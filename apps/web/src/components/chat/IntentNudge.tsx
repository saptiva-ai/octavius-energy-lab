import { Button } from '../ui/Button'

interface IntentNudgeProps {
  message: string
  onDismiss: () => void
}

export function IntentNudge({ message, onDismiss }: IntentNudgeProps) {
  return (
    <div className="mb-4 w-full max-w-3xl rounded-2xl border border-primary/30 bg-primary/10 px-4 py-3 text-sm text-primary">
      <div className="flex items-start justify-between gap-3">
        <p className="leading-relaxed">{message}</p>
        <Button variant="ghost" size="sm" onClick={onDismiss}>
          Entendido
        </Button>
      </div>
    </div>
  )
}
