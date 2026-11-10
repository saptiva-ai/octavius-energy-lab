// Force dynamic rendering and disable caching in development
export const dynamic = 'force-dynamic';
export const revalidate = 0;
export const fetchCache = 'force-no-store';
export const runtime = 'nodejs';

import { Suspense } from 'react'

import { assertProdNoMock } from '../../lib/runtime'
import { ChatView } from './_components/ChatView'

assertProdNoMock()

export default function ChatPage() {
  return (
    <Suspense fallback={null}>
      <ChatView />
    </Suspense>
  )
}
