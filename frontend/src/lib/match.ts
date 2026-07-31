// match_score=50 es "sin evidencia" por diseño del backend (recommender.py:
// match_score = round(50 + 49*tanh(points/40)), points=0 → 50 exacto) — un
// número que parece preciso pero no lo es. Pedido de Matías (2026-07-31):
// mostrar "Match desconocido" en vez de "50% match" en ese caso.
export function isUnknownMatch(matchScore: number): boolean {
  return matchScore === 50;
}
