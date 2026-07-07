import type { ReactNode } from 'react'

interface Props {
  title: string
  subtitle?: string
  children: ReactNode
}

export function AuthLayout({ title, subtitle, children }: Props) {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <div className="flex flex-col items-center gap-2 mb-6">
          <img src="/brand/icon.svg" alt="" className="h-8 w-8" />
          <span className="font-semibold text-gray-900 text-lg">rapport</span>
        </div>
        <div className="rounded-2xl bg-white shadow-sm border border-gray-100 p-6">
          <h1 className="text-sm font-semibold text-gray-800 mb-1">{title}</h1>
          {subtitle && <p className="text-xs text-gray-400 mb-4">{subtitle}</p>}
          {children}
        </div>
      </div>
    </div>
  )
}

export const authInputClass =
  'w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'

export const authButtonClass =
  'w-full rounded-lg bg-indigo-600 text-white text-sm font-medium py-2 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors'

export function AuthError({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg bg-red-50 border border-red-100 px-3 py-2 text-xs text-red-700 mb-4">
      {message}
    </div>
  )
}

export function AuthSuccess({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg bg-green-50 border border-green-100 px-3 py-2 text-xs text-green-700 mb-4">
      {message}
    </div>
  )
}
