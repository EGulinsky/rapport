import { ApiError } from '../api/client'

/** Renders a caught error for display: translates ApiError.errorKey via the
 * `errors` namespace when present, falling back to the caught error's own
 * message (German prose from the backend) for anything not yet keyed —
 * e.g. tier-2 dynamic messages (SMTP/sync errors) or a plain network error. */
export function errorMessage(err: unknown, t: (key: string, fallback: string) => string): string {
  if (err instanceof ApiError && err.errorKey) {
    return t(`errors:${err.errorKey}`, err.message)
  }
  return err instanceof Error ? err.message : String(err)
}
