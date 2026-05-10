// DataInsightGrove — Mac wrapper.
//
// On launch:
//   1. Run scripts/dig-start.sh and wait for the API + web servers to be ready.
//   2. Open a WKWebView window pointing at the configured web URL.
//
// On quit (Cmd-Q, window close, app termination):
//   3. Run scripts/dig-stop.sh to bring everything down cleanly.
//
// The repo path is baked into the bundle via Info.plist's `DIGRepoRoot`
// at build time. URLs come from `scripts/dig_config.py export` so the app
// honors the same config.json as the shell scripts.

import AppKit
import WebKit

// MARK: - Helpers

func bundleRepoRoot() -> String {
    if let v = Bundle.main.object(forInfoDictionaryKey: "DIGRepoRoot") as? String, !v.isEmpty {
        return (v as NSString).expandingTildeInPath
    }
    // Fallback: assume the .app sits inside <repo>/mac/build/
    let appPath = Bundle.main.bundlePath as NSString
    return appPath.deletingLastPathComponent  // …/build
        .components(separatedBy: "/mac/build").first ?? "/"
}

func runScript(_ name: String, args: [String] = []) -> (status: Int32, output: String) {
    let repo = bundleRepoRoot()
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "\(repo)/scripts/\(name)")
    task.arguments = args
    let pipe = Pipe()
    task.standardOutput = pipe
    task.standardError = pipe
    do {
        try task.run()
    } catch {
        return (-1, "could not exec \(name): \(error)")
    }
    task.waitUntilExit()
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    let out = String(data: data, encoding: .utf8) ?? ""
    return (task.terminationStatus, out)
}

func resolvedWebURL() -> URL {
    // scripts/dig_config.py export → KEY=VALUE lines
    let repo = bundleRepoRoot()
    let task = Process()
    task.executableURL = URL(fileURLWithPath: "/usr/bin/env")
    task.arguments = ["python3", "\(repo)/scripts/dig_config.py", "export"]
    let pipe = Pipe()
    task.standardOutput = pipe
    task.standardError = Pipe()
    do { try task.run() } catch {
        return URL(string: "http://127.0.0.1:3000")!
    }
    task.waitUntilExit()
    let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
    var host = "127.0.0.1"
    var port = "3000"
    for line in out.split(separator: "\n") {
        let parts = line.split(separator: "=", maxSplits: 1).map(String.init)
        guard parts.count == 2 else { continue }
        let key = parts[0]
        let value = parts[1].trimmingCharacters(in: CharacterSet(charactersIn: "'\""))
        switch key {
        case "DIG_WEB_HOST": host = value
        case "DIG_WEB_PORT": port = value
        default: break
        }
    }
    return URL(string: "http://\(host):\(port)") ?? URL(string: "http://127.0.0.1:3000")!
}

// MARK: - Splash window (shown while dig-start.sh boots)

final class SplashWindow: NSWindow {
    let label: NSTextField

    override init(contentRect: NSRect, styleMask: StyleMask, backing: BackingStoreType, defer flag: Bool) {
        let label = NSTextField(labelWithString: "🌳 Starting DataInsightGrove…")
        self.label = label
        super.init(contentRect: contentRect, styleMask: styleMask, backing: backing, defer: flag)
    }

    func setStatus(_ text: String) {
        DispatchQueue.main.async { self.label.stringValue = text }
    }

    static func make() -> SplashWindow {
        let w = SplashWindow(
            contentRect: NSRect(x: 0, y: 0, width: 480, height: 200),
            styleMask: [.titled, .closable],
            backing: .buffered, defer: false
        )
        w.title = "DataInsightGrove"
        w.center()
        let view = NSView(frame: w.contentRect(forFrameRect: w.frame))
        view.wantsLayer = true
        view.layer?.backgroundColor = NSColor(srgbRed: 0.02, green: 0.06, blue: 0.04, alpha: 1).cgColor

        let title = NSTextField(labelWithString: "🌳 DataInsightGrove")
        title.font = NSFont.systemFont(ofSize: 22, weight: .semibold)
        title.textColor = .white
        title.alignment = .center
        title.frame = NSRect(x: 0, y: 110, width: 480, height: 40)
        view.addSubview(title)

        w.label.font = NSFont.systemFont(ofSize: 13, weight: .regular)
        w.label.textColor = NSColor(white: 0.85, alpha: 1)
        w.label.alignment = .center
        w.label.frame = NSRect(x: 20, y: 60, width: 440, height: 22)
        view.addSubview(w.label)

        let hint = NSTextField(labelWithString: "first launch can take ~5 seconds while the engine warms up")
        hint.font = NSFont.systemFont(ofSize: 11)
        hint.textColor = NSColor(white: 0.55, alpha: 1)
        hint.alignment = .center
        hint.frame = NSRect(x: 20, y: 30, width: 440, height: 18)
        view.addSubview(hint)

        w.contentView = view
        return w
    }
}

// MARK: - Main browser window

/// NSWindow subclass that intercepts left mouse-down events in the top
/// `dragHeight` points of the window and converts them into a window drag
/// (or zoom on double-click).
///
/// Why a `sendEvent` override and not the usual `mouseDownCanMoveWindow`
/// trick on a transparent overlay view: WKWebView is a layer-hosting view
/// with its own NSTrackingAreas + an internal child view that handles
/// text selection. In practice those win the hit-test race against any
/// sibling NSView we add on top — left-click in the top strip falls
/// through to WKWebView and gets interpreted as text selection (the
/// "first word highlights on double-click" symptom). Intercepting at
/// `sendEvent(_:)` runs BEFORE view-tree dispatch, so WKWebView never
/// sees the event and the drag is reliable.
///
/// Traffic-light buttons (close / minimize / zoom) live in the window's
/// chrome view hierarchy and are processed before `sendEvent` is called,
/// so they remain clickable normally.
final class DraggableTopWindow: NSWindow {
    /// Height of the top strip that triggers a window drag. ~28pt matches
    /// the standard macOS title-bar height.
    static let dragHeight: CGFloat = 28

    override func sendEvent(_ event: NSEvent) {
        if event.type == .leftMouseDown {
            // `locationInWindow` origin = bottom-left of the content area.
            // With .fullSizeContentView the content area == the whole window,
            // so frame.height is the right reference for the top edge.
            let pt = event.locationInWindow
            if pt.y >= frame.height - Self.dragHeight,
               !isPointOnStandardWindowButton(pt) {
                // Above the strip AND not on a traffic-light button.
                if event.clickCount == 2 {
                    // Double-click on the title bar = zoom (matches the
                    // System Settings "Double-click a window's title bar
                    // to: Zoom" default).
                    performZoom(nil)
                } else {
                    performDrag(with: event)
                }
                return
            }
        }
        super.sendEvent(event)
    }

    /// Returns true if `pt` (in window coordinates) lies inside one of the
    /// standard window buttons (close / minimize / zoom). Those need to
    /// fall through to AppKit's normal dispatch so clicking them actually
    /// closes / minimizes / zooms the window — without this guard our
    /// `performDrag` swallows the click and the traffic lights look broken.
    private func isPointOnStandardWindowButton(_ pt: NSPoint) -> Bool {
        for kind: NSWindow.ButtonType in [.closeButton, .miniaturizeButton, .zoomButton] {
            guard let btn = standardWindowButton(kind) else { continue }
            // Convert the button's local bounds into window coordinates so
            // we can compare with `event.locationInWindow`.
            let frameInWindow = btn.convert(btn.bounds, to: nil)
            // Inflate the hit area slightly (4pt) so the edges of the
            // buttons feel right under the cursor — matches what AppKit
            // does internally.
            if frameInWindow.insetBy(dx: -4, dy: -4).contains(pt) {
                return true
            }
        }
        return false
    }
}

final class BrowserWindowController: NSWindowController {
    let webView: WKWebView

    init(url: URL) {
        let cfg = WKWebViewConfiguration()
        cfg.preferences.javaScriptCanOpenWindowsAutomatically = false

        // Tell the web app it's running inside the Mac wrapper, BEFORE any
        // page JS runs. The frontend reads this to:
        //   - reserve the top 28pt for the title-bar / traffic-light zone
        //     (CSS variable --dig-titlebar-h flips from 0px to 28px)
        //   - render the MacTitlebar brand strip on the right of the lights
        // The dataset attribute on <html> is the workhorse — it lets pure
        // CSS branch on Mac mode without waiting for client-side JS, so
        // the layout is correct on the very first paint.
        let macFlagScript = WKUserScript(
            source: """
            window.__DIG_MAC__ = true;
            document.documentElement.dataset.digMac = 'true';
            """,
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        )
        cfg.userContentController.addUserScript(macFlagScript)

        let web = WKWebView(frame: .zero, configuration: cfg)
        self.webView = web

        let win = DraggableTopWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1280, height: 820),
            styleMask: [.titled, .closable, .resizable, .miniaturizable, .fullSizeContentView],
            backing: .buffered, defer: false
        )
        win.title = "DataInsightGrove"
        win.titleVisibility = .hidden                  // hide the centered title text
        win.titlebarAppearsTransparent = true          // modern chrome-less look
        win.center()
        win.contentView = web
        super.init(window: win)
        web.load(URLRequest(url: url))
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) not used") }
}

// MARK: - App delegate

final class AppDelegate: NSObject, NSApplicationDelegate {
    var splash: SplashWindow?
    var browser: BrowserWindowController?
    var didStart = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        let splash = SplashWindow.make()
        splash.makeKeyAndOrderFront(nil)
        self.splash = splash

        DispatchQueue.global(qos: .userInitiated).async {
            // Already running? dig-start exits 2; we just open the browser instead.
            splash.setStatus("Launching backend + web…")
            let result = runScript("dig-start.sh")
            self.didStart = (result.status == 0)
            if !self.didStart && result.status != 2 {
                splash.setStatus("⚠️ start failed (exit \(result.status)) — see Console")
                NSLog("dig-start.sh failed:\n%@", result.output)
                return
            }
            splash.setStatus("Connecting to UI…")
            let url = resolvedWebURL()
            DispatchQueue.main.async {
                let bc = BrowserWindowController(url: url)
                self.browser = bc
                bc.showWindow(nil)
                splash.orderOut(nil)
                self.splash = nil
                NSApp.activate(ignoringOtherApps: true)
            }
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        // Only stop what *we* started. If the user pre-started via the shell
        // script (status 2 = port busy when we ran), leave it alone.
        if didStart {
            _ = runScript("dig-stop.sh")
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

// MARK: - Bootstrap

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.activate(ignoringOtherApps: true)
app.run()
