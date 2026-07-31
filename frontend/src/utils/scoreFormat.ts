// Shared color band for the AI match_score/success_probability badges
// (KanbanBoard card + ApplicationTable columns) — >=70 green, 40-69 yellow,
// <40 red, reusing the existing status-color Tailwind conventions rather
// than introducing a new palette.
export function scoreColorClass(score: number): string {
  if (score >= 70) return 'text-green-600'
  if (score >= 40) return 'text-yellow-600'
  return 'text-red-600'
}
