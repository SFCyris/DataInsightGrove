import type {
  PipelineDocument,
  PipelineNode,
  StepManifest,
} from "@/lib/api/client";
import type { Edge, Node } from "@xyflow/react";

let _idCounter = 0;
function newId(prefix: string): string {
  _idCounter++;
  return `${prefix}_${Date.now().toString(36)}${_idCounter.toString(36)}`;
}

export function emptyDoc(id: string, name: string): PipelineDocument {
  return {
    schemaVersion: 1,
    id,
    name,
    datasets: [],
    nodes: [],
    outputs: [],
  };
}

/** Build React Flow nodes + edges from a pipeline document. */
export function docToFlow(
  doc: PipelineDocument,
  manifests: Record<string, StepManifest>,
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  // Datasets — left column.
  doc.datasets.forEach((d, idx) => {
    nodes.push({
      id: d.id,
      type: "dataset",
      position: { x: 40, y: 40 + idx * 110 },
      data: {
        kind: "dataset",
        label: d.label || d.id,
        connector: d.connector,
        uri: d.uri,
      },
    });
  });

  // Step nodes — laid out from doc.ui or default cascade.
  doc.nodes.forEach((n, idx) => {
    const manifest = manifests[n.step];
    const inputPorts = manifest?.io.inputs.ports ?? Object.keys(n.inputs).length ? Object.keys(n.inputs) : ["in"];
    const outputPorts = manifest?.io.outputs.ports ?? n.outputs;
    const x = n.ui?.x ?? 280 + idx * 220;
    const y = n.ui?.y ?? 60 + (idx % 4) * 100;
    nodes.push({
      id: n.id,
      type: "step",
      position: { x, y },
      data: {
        kind: "step",
        label: manifest?.label ?? n.step,
        category: manifest?.category ?? "custom",
        step: n.step,
        inputPorts,
        outputPorts,
      },
    });

    // Edges from each declared input.
    Object.entries(n.inputs).forEach(([port, ref]) => {
      edges.push({
        id: `${ref.ref}-${ref.port ?? "out"}__${n.id}-${port}`,
        source: ref.ref,
        sourceHandle: ref.port ?? "out",
        target: n.id,
        targetHandle: port,
        animated: false,
      });
    });
  });

  // Output sinks.
  doc.outputs.forEach((o, idx) => {
    const x = 980 + idx * 200;
    const y = 60 + idx * 80;
    nodes.push({
      id: o.id,
      type: "output",
      position: { x, y },
      data: { kind: "output", label: o.name, sink: o.sink?.connector ?? null },
    });
    edges.push({
      id: `${o.from.ref}-${o.from.port ?? "out"}__${o.id}-out`,
      source: o.from.ref,
      sourceHandle: o.from.port ?? "out",
      target: o.id,
      targetHandle: "out",
    });
  });

  return { nodes, edges };
}

/** Apply the current React Flow node positions back into a doc. */
export function applyPositions(doc: PipelineDocument, flowNodes: Node[]): PipelineDocument {
  const byId = new Map(flowNodes.map((n) => [n.id, n]));
  return {
    ...doc,
    nodes: doc.nodes.map((n) => {
      const fn = byId.get(n.id);
      if (!fn) return n;
      return {
        ...n,
        ui: { ...(n.ui ?? {}), x: fn.position.x, y: fn.position.y },
      };
    }),
  };
}

export function addStep(
  doc: PipelineDocument,
  manifest: StepManifest,
  position: { x: number; y: number },
): { doc: PipelineDocument; nodeId: string } {
  const id = newId("n");
  const node: PipelineNode = {
    id,
    step: manifest.id,
    stepVersion: manifest.version,
    inputs: {},
    outputs: manifest.io.outputs.ports ?? ["out"],
    params: {},
    ui: { x: position.x, y: position.y, label: manifest.label },
  };
  return { doc: { ...doc, nodes: [...doc.nodes, node] }, nodeId: id };
}

export function removeNode(doc: PipelineDocument, nodeId: string): PipelineDocument {
  return {
    ...doc,
    datasets: doc.datasets.filter((d) => d.id !== nodeId),
    nodes: doc.nodes
      .filter((n) => n.id !== nodeId)
      .map((n) => ({
        ...n,
        inputs: Object.fromEntries(
          Object.entries(n.inputs).filter(([_, ref]) => ref.ref !== nodeId),
        ),
      })),
    outputs: doc.outputs.filter((o) => o.from.ref !== nodeId && o.id !== nodeId),
  };
}

export function connectEdge(
  doc: PipelineDocument,
  source: string,
  sourcePort: string,
  target: string,
  targetPort: string,
): PipelineDocument {
  // Connecting to an output node is a special case (target is in doc.outputs).
  const outputIdx = doc.outputs.findIndex((o) => o.id === target);
  if (outputIdx !== -1) {
    const outs = [...doc.outputs];
    outs[outputIdx] = { ...outs[outputIdx], from: { ref: source, port: sourcePort } };
    return { ...doc, outputs: outs };
  }
  return {
    ...doc,
    nodes: doc.nodes.map((n) =>
      n.id === target
        ? { ...n, inputs: { ...n.inputs, [targetPort]: { ref: source, port: sourcePort } } }
        : n,
    ),
  };
}

export function setNodeParams(
  doc: PipelineDocument,
  nodeId: string,
  params: Record<string, unknown>,
): PipelineDocument {
  return {
    ...doc,
    nodes: doc.nodes.map((n) => (n.id === nodeId ? { ...n, params } : n)),
  };
}

/** Toggle exposure of a node's param for sub-pipeline composition.
 *
 *  When `next` is non-null, sets `node.ui.exposedParams[paramKey]`.
 *  When `next` is null, removes that key (and the whole `exposedParams`
 *  object if it becomes empty, to keep the doc tidy).
 *
 *  Mirrors `setNodeParams` so the editor can call it the same way.
 */
export function setNodeExposedParam(
  doc: PipelineDocument,
  nodeId: string,
  paramKey: string,
  next: { alias: string; help?: string } | null,
): PipelineDocument {
  return {
    ...doc,
    nodes: doc.nodes.map((n) => {
      if (n.id !== nodeId) return n;
      // PipelineNode.ui only declares the canvas-render fields (x/y/label/
      // note) but the saved doc carries `exposedParams` as a free-form
      // extension. Cast through `unknown` so TS doesn't try to reconcile
      // the two shapes; the runtime layout is one merged object either way.
      const ui = (n.ui ?? {}) as unknown as {
        x?: number; y?: number; label?: string; note?: string;
        exposedParams?: Record<string, unknown>;
      };
      const exposed = { ...(ui.exposedParams ?? {}) };
      if (next === null) {
        delete exposed[paramKey];
      } else {
        exposed[paramKey] = next;
      }
      const nextUi: typeof ui = { ...ui };
      if (Object.keys(exposed).length === 0) {
        delete nextUi.exposedParams;
      } else {
        nextUi.exposedParams = exposed;
      }
      return { ...n, ui: nextUi as typeof n.ui };
    }),
  };
}

export function ensureTerminalOutput(doc: PipelineDocument): PipelineDocument {
  if (doc.outputs.length > 0 || doc.nodes.length === 0) return doc;
  const last = doc.nodes[doc.nodes.length - 1];
  return {
    ...doc,
    outputs: [
      {
        id: `o_${last.id}`,
        name: "result",
        from: { ref: last.id, port: last.outputs[0] ?? "out" },
      },
    ],
  };
}
