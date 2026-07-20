// Shared by KanbanBoard.tsx and ApplicationModal.tsx -- formats the cached
// car-navigation distance/duration from home to a job's location
// (Application.drive_distance_km/drive_duration_min).
export function formatDriveDistance(km: number, durationMin: number): string {
  const hours = durationMin / 60
  return `${Math.round(km)} km · ${hours.toFixed(1)} h`
}
