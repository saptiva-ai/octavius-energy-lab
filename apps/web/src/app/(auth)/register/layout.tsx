import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Registro no disponible | OctaviOS',
  robots: {
    index: false,
    follow: false,
  },
}

export default function RegisterLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
