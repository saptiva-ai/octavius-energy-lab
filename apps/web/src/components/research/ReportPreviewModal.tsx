'use client'

import * as React from 'react'
import {
  XMarkIcon as X,
  ArrowDownTrayIcon as Download,
  ShareIcon as Share2,
  DocumentTextIcon as FileText,
  GlobeAltIcon as Globe,
  PhotoIcon as FileImage
} from '@heroicons/react/24/outline'
import { Button, Modal } from '../ui'
import { useApiClient } from '../../lib/api-client'
import { logError, logInfo } from '../../lib/logger'

interface ReportPreviewModalProps {
  taskId: string
  isOpen: boolean
  onClose: () => void
  taskTitle?: string
}

interface ReportMetadata {
  task_id: string
  status: string
  created_at: string
  completed_at?: string
  report_size: number
  available_formats: string[]
  shareable_url?: string
  url_expires_at?: string
}

const formatIcons = {
  md: FileText,
  html: Globe,
  pdf: FileImage
}

export function ReportPreviewModal({
  taskId,
  isOpen,
  onClose,
  taskTitle = "Research Report"
}: ReportPreviewModalProps) {
  const apiClient = useApiClient()
  const [metadata, setMetadata] = React.useState<ReportMetadata | null>(null)
  const [previewContent, setPreviewContent] = React.useState<string>('')
  const [selectedFormat, setSelectedFormat] = React.useState<'md' | 'html' | 'pdf'>('html')
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [shareableUrl, setShareableUrl] = React.useState<string | null>(null)

  const loadReportMetadata = React.useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await apiClient.getReportMetadata(taskId)
      setMetadata(response)

      // Set default format to the first available, preferring HTML
      const availableFormats = response.available_formats || ['html', 'md', 'pdf']
      const defaultFormat = availableFormats.includes('html') ? 'html' : availableFormats[0]
      setSelectedFormat(defaultFormat as typeof selectedFormat)

    } catch (err) {
      logError('Failed to load report metadata:', err)
      setError('Failed to load report information')
    } finally {
      setLoading(false)
    }
  }, [apiClient, taskId])

  const loadPreview = React.useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      // Create preview URL
      const previewUrl = `/api/report/${taskId}/preview?format=${selectedFormat}&include_sources=true`

      // Fetch preview content
      const response = await fetch(previewUrl, {
        cache: 'no-store',
        headers: {
          'Authorization': `Bearer ${apiClient.getToken() || ''}`,
          'Cache-Control': 'no-store',
          'Pragma': 'no-cache',
        },
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const content = await response.text()
      setPreviewContent(content)

    } catch (err) {
      logError('Failed to load preview:', err)
      setError('Failed to load report preview')
    } finally {
      setLoading(false)
    }
  }, [apiClient, selectedFormat, taskId])

  // Load report metadata when modal opens
  React.useEffect(() => {
    if (isOpen && taskId) {
      loadReportMetadata()
    }
  }, [isOpen, taskId, loadReportMetadata])

  // Load preview when format changes
  React.useEffect(() => {
    if (isOpen && taskId && selectedFormat) {
      loadPreview()
    }
  }, [isOpen, taskId, selectedFormat, loadPreview])

  const handleDownload = async () => {
    try {
      const blob = await apiClient.downloadReport(taskId, selectedFormat, true)

      // Create download link
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `research-report-${taskId}.${selectedFormat}`

      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)

      window.URL.revokeObjectURL(url)
    } catch (err) {
      logError('Download failed:', err)
      setError('Failed to download report')
    }
  }

  const handleShare = async () => {
    try {
      const response = await fetch(`/api/report/${taskId}/share`, {
        method: 'POST',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiClient.getToken() || ''}`,
          'Cache-Control': 'no-store',
          'Pragma': 'no-cache',
        },
        body: JSON.stringify({
          format: selectedFormat,
          expires_in_hours: 24
        })
      })

      if (response.ok) {
        const data = await response.json()
        setShareableUrl(data.shareable_url)

        // Copy to clipboard
        await navigator.clipboard.writeText(data.shareable_url)

        // Could show a toast notification here
        logInfo('Shareable link copied to clipboard')
      }
    } catch (err) {
      logError('Share failed:', err)
      setError('Failed to create shareable link')
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const isFormatAvailable = (format: string) => {
    return metadata?.available_formats?.includes(format) ?? false
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose} size="xl" showCloseButton={false}>
      <div className="flex flex-col h-[80vh] -mx-6 -my-4">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">
              {taskTitle}
            </h2>
            <p className="text-sm text-gray-500 mt-1">
              Task ID: {taskId}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        {/* Format selector and actions */}
        <div className="flex items-center justify-between p-4 bg-gray-50 border-b border-gray-200">
          <div className="flex items-center space-x-4">
            <span className="text-sm font-medium text-gray-700">Format:</span>
            <div className="flex space-x-2">
              {['html', 'md', 'pdf'].map((format) => {
                const Icon = formatIcons[format as keyof typeof formatIcons]
                const available = isFormatAvailable(format)

                return (
                  <button
                    key={format}
                    onClick={() => available && setSelectedFormat(format as typeof selectedFormat)}
                    disabled={!available}
                    className={`flex items-center space-x-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                      selectedFormat === format
                        ? 'bg-saptiva-mint text-white'
                        : available
                        ? 'bg-white text-gray-700 hover:bg-gray-100'
                        : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span>{format.toUpperCase()}</span>
                  </button>
                )
              })}
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleShare}
              disabled={loading}
            >
              <Share2 className="h-4 w-4 mr-2" />
              Share
            </Button>
            <Button
              size="sm"
              onClick={handleDownload}
              disabled={loading}
            >
              <Download className="h-4 w-4 mr-2" />
              Download
            </Button>
          </div>
        </div>

        {/* Metadata */}
        {metadata && (
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <div className="flex items-center space-x-6 text-sm text-gray-600">
              <span>
                Created: {new Date(metadata.created_at).toLocaleDateString()}
              </span>
              {metadata.completed_at && (
                <span>
                  Completed: {new Date(metadata.completed_at).toLocaleDateString()}
                </span>
              )}
              <span>
                Size: {formatFileSize(metadata.report_size)}
              </span>
              <span className="capitalize">
                Status: {metadata.status}
              </span>
            </div>
          </div>
        )}

        {/* Preview content */}
        <div className="flex-1 overflow-hidden">
          {error ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <p className="text-red-600 font-medium">Error loading report</p>
                <p className="text-sm text-gray-500 mt-1">{error}</p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={loadPreview}
                  className="mt-4"
                >
                  Retry
                </Button>
              </div>
            </div>
          ) : loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="animate-spin h-8 w-8 border-4 border-saptiva-mint border-t-transparent rounded-full mx-auto"></div>
                <p className="text-gray-500 mt-3">Loading preview...</p>
              </div>
            </div>
          ) : (
            <div className="h-full overflow-auto p-6">
              {selectedFormat === 'html' ? (
                <div
                  className="prose prose-sm max-w-none"
                  dangerouslySetInnerHTML={{ __html: previewContent }}
                />
              ) : selectedFormat === 'pdf' ? (
                <div className="text-center py-8">
                  <FileImage className="h-16 w-16 text-gray-400 mx-auto mb-4" />
                  <p className="text-gray-600">PDF preview not available in browser</p>
                  <p className="text-sm text-gray-500 mt-1">Click download to view the PDF file</p>
                </div>
              ) : (
                <pre className="whitespace-pre-wrap text-sm text-gray-800 font-mono">
                  {previewContent}
                </pre>
              )}
            </div>
          )}
        </div>

        {/* Shareable link display */}
        {shareableUrl && (
          <div className="p-4 bg-green-50 border-t border-green-200">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-green-800">Shareable link created!</p>
                <p className="text-xs text-green-600 mt-1">Link copied to clipboard (expires in 24 hours)</p>
              </div>
              <button
                onClick={() => navigator.clipboard.writeText(shareableUrl)}
                className="text-sm text-green-700 hover:text-green-900 underline"
              >
                Copy again
              </button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}
