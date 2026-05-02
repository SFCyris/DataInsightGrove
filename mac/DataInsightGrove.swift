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

final class BrowserWindowController: NSWindowController {
    let webView: WKWebView

    init(url: URL) {
        let cfg = WKWebViewConfiguration()
        cfg.preferences.javaScriptCanOpenWindowsAutomatically = false
        let web = WKWebView(frame: .zero, configuration: cfg)
        self.webView = web

        let win = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1280, height: 820),
            styleMask: [.titled, .closable, .resizable, .miniaturizable, .fullSizeContentView],
            backing: .buffered, defer: false
        )
        win.title = "DataInsightGrove"
        win.titlebarAppearsTransparent = true
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
