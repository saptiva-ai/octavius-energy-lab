import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="flex h-screen items-center justify-center bg-saptiva-dark">
      <div className="text-center">
        <h1 className="text-4xl font-bold text-white mb-4">Conversación no encontrada</h1>
        <p className="text-saptiva-light/70 mb-8">
          La conversación que buscas no existe o no tienes acceso a ella.
        </p>
        <Link
          href="/chat"
          className="inline-flex items-center justify-center rounded-full bg-saptiva-blue px-6 py-3 text-sm font-semibold text-white hover:bg-saptiva-lightBlue/90 transition-colors"
        >
          Volver al chat
        </Link>
      </div>
    </div>
  )
}