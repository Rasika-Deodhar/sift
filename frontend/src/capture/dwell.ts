// Dwell tracking: how long each item stays on screen, accumulated across re-appearances.

export class DwellTracker {
  private totals = new Map<string, number>();
  private active: { itemId: string; since: number } | null = null;

  enter(itemId: string, t: number): void {
    if (this.active) this.leave(t);
    this.active = { itemId, since: t };
  }

  /** Ends the active item and returns its accumulated dwell. */
  leave(t: number): { itemId: string; dwellMs: number } | null {
    if (!this.active) return null;
    const { itemId, since } = this.active;
    const total = (this.totals.get(itemId) ?? 0) + Math.max(0, t - since);
    this.totals.set(itemId, total);
    this.active = null;
    return { itemId, dwellMs: total };
  }

  /** Live dwell for display, including the time in the current visit. */
  current(itemId: string, t: number): number {
    const base = this.totals.get(itemId) ?? 0;
    return this.active?.itemId === itemId ? base + (t - this.active.since) : base;
  }

  reset(): void {
    this.totals.clear();
    this.active = null;
  }
}
