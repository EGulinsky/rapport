// Injected at Docker build time via VITE_BUILD_NUMBER env var (set from github.run_number).
// Falls back to "dev" when running locally without the arg.
export const BUILD_NUMBER: string = import.meta.env.VITE_BUILD_NUMBER || 'dev'

export function formatVersion(version: string): string {
  return `${version} (Build ${BUILD_NUMBER})`
}
