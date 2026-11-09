import type { GraphEdge, GraphPosition } from "./graphTypes";
type Position = GraphPosition;
type Point = Position & { vx: number; vy: number };

// Small, bounded local projections (60 nodes). Physics never touches knowledge data.
export class ForceSimulation {
  points: Map<string, Point>;
  alpha = 0;
  dragging: string | null = null;
  constructor(
    positions: Position[],
    private edges: Pick<GraphEdge, "source" | "target">[],
  ) {
    this.points = new Map(
      positions.map((p) => [p.node_id, { ...p, vx: 0, vy: 0 }]),
    );
  }
  wake() {
    this.alpha = 0.75;
  }
  move(id: string, x: number, y: number) {
    const p = this.points.get(id);
    if (p && Number.isFinite(x) && Number.isFinite(y)) {
      p.x = x;
      p.y = y;
      p.vx = p.vy = 0;
      this.dragging = id;
      this.wake();
    }
  }
  pin(id: string) {
    const p = this.points.get(id);
    if (p) {
      p.pinned = !p.pinned;
      p.vx = p.vy = 0;
      this.wake();
    }
  }
  snapshot(): Position[] {
    return [...this.points.values()].map(({ node_id, x, y, pinned }) => ({
      node_id,
      x,
      y,
      pinned,
    }));
  }
  tick() {
    if (this.alpha < 0.005 && !this.dragging) return false;
    const ps = [...this.points.values()];
    const forces = new Map(ps.map((p) => [p.node_id, { x: 0, y: 0 }]));
    for (let i = 0; i < ps.length; i++)
      for (let j = i + 1; j < ps.length; j++) {
        const dx = ps[i].x - ps[j].x || 0.1;
        const dy = ps[i].y - ps[j].y || 0.1;
        const distance = Math.max(4, Math.hypot(dx, dy));
        const magnitude = Math.min(
          12,
          2600 / (distance * distance) + Math.max(0, 50 - distance) * 0.12,
        );
        const a = forces.get(ps[i].node_id)!,
          b = forces.get(ps[j].node_id)!;
        a.x += (dx / distance) * magnitude;
        a.y += (dy / distance) * magnitude;
        b.x -= (dx / distance) * magnitude;
        b.y -= (dy / distance) * magnitude;
      }
    for (const edge of this.edges) {
      const a = this.points.get(edge.source),
        b = this.points.get(edge.target);
      if (!a || !b) continue;
      const dx = b.x - a.x,
        dy = b.y - a.y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const magnitude = (distance - 115) * 0.035;
      const af = forces.get(a.node_id)!,
        bf = forces.get(b.node_id)!;
      af.x += (dx / distance) * magnitude;
      af.y += (dy / distance) * magnitude;
      bf.x -= (dx / distance) * magnitude;
      bf.y -= (dy / distance) * magnitude;
    }
    for (const p of ps) {
      if (p.pinned || p.node_id === this.dragging) continue;
      const f = forces.get(p.node_id)!;
      p.vx = (p.vx + f.x * this.alpha) * 0.7;
      p.vy = (p.vy + f.y * this.alpha) * 0.7;
      p.x += Math.max(-14, Math.min(14, p.vx));
      p.y += Math.max(-14, Math.min(14, p.vy));
    }
    this.alpha *= this.dragging ? 0.99 : 0.965;
    if (this.dragging) this.alpha = Math.max(this.alpha, 0.25);
    return true;
  }
}
