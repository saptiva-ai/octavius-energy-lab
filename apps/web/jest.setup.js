import '@testing-library/jest-dom'

// Mock Next.js router
jest.mock('next/router', () => ({
  useRouter() {
    return {
      route: '/',
      pathname: '/',
      query: {},
      asPath: '/',
      push: jest.fn(),
      pop: jest.fn(),
      reload: jest.fn(),
      back: jest.fn(),
      prefetch: jest.fn().mockResolvedValue(undefined),
      beforePopState: jest.fn(),
      events: {
        on: jest.fn(),
        off: jest.fn(),
        emit: jest.fn(),
      },
      isFallback: false,
    }
  },
}))

// Mock Next.js navigation
jest.mock('next/navigation', () => ({
  useRouter() {
    return {
      push: jest.fn(),
      replace: jest.fn(),
      prefetch: jest.fn(),
      back: jest.fn(),
      forward: jest.fn(),
      refresh: jest.fn(),
    }
  },
  useSearchParams() {
    return new URLSearchParams()
  },
  usePathname() {
    return '/'
  },
}))

// Mock IntersectionObserver
global.IntersectionObserver = class IntersectionObserver {
  constructor() {}
  disconnect() {}
  observe() {}
  unobserve() {}
}

// Mock ResizeObserver
global.ResizeObserver = class ResizeObserver {
  constructor() {}
  disconnect() {}
  observe() {}
  unobserve() {}
}

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(), // deprecated
    removeListener: jest.fn(), // deprecated
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
})

// Mock EventSource for SSE testing
global.EventSource = class EventSource {
  constructor(url) {
    this.url = url
    this.readyState = 1
    setTimeout(() => {
      if (this.onopen) this.onopen()
    }, 10)
  }
  close() {
    this.readyState = 2
  }
  addEventListener() {}
  removeEventListener() {}
}

// Mock performance.now for timing tests
global.performance = global.performance || {}
global.performance.now = jest.fn(() => Date.now())

// Polyfill Response and Headers for fetch tests
if (typeof global.Response === 'undefined') {
  global.Response = class Response {
    constructor(body, init = {}) {
      this._body = body
      this.status = init.status || 200
      this.statusText = init.statusText || 'OK'
      this.headers = new Headers(init.headers || {})
      this.ok = this.status >= 200 && this.status < 300
      this._bodyUsed = false
    }

    get body() {
      return this._body
    }

    get bodyUsed() {
      return this._bodyUsed
    }

    async json() {
      this._bodyUsed = true
      return typeof this._body === 'string' ? JSON.parse(this._body) : this._body
    }

    async text() {
      this._bodyUsed = true
      return typeof this._body === 'string' ? this._body : JSON.stringify(this._body)
    }

    clone() {
      return new Response(this._body, {
        status: this.status,
        statusText: this.statusText,
        headers: Object.fromEntries(this.headers.entries()),
      })
    }
  }
}

if (typeof global.Headers === 'undefined') {
  global.Headers = class Headers {
    constructor(init = {}) {
      this._headers = {}
      if (init) {
        Object.entries(init).forEach(([key, value]) => {
          this._headers[key.toLowerCase()] = value
        })
      }
    }

    get(name) {
      return this._headers[name.toLowerCase()] || null
    }

    set(name, value) {
      this._headers[name.toLowerCase()] = value
    }

    has(name) {
      return name.toLowerCase() in this._headers
    }

    entries() {
      return Object.entries(this._headers)
    }
  }
}

// Polyfill TextEncoder/TextDecoder for hash tests
if (typeof global.TextEncoder === 'undefined') {
  const { TextEncoder, TextDecoder } = require('util')
  global.TextEncoder = TextEncoder
  global.TextDecoder = TextDecoder
}

// Polyfill crypto.subtle for Web Crypto API tests
if (typeof global.crypto === 'undefined' || !global.crypto.subtle) {
  const nodeCrypto = require('crypto')

  // Wrapper to handle ArrayBuffer from jsdom context
  const originalDigest = nodeCrypto.webcrypto.subtle.digest.bind(nodeCrypto.webcrypto.subtle)
  const wrappedDigest = async (algorithm, data) => {
    // Convert jsdom ArrayBuffer to Node.js Buffer
    let buffer = data
    if (data instanceof ArrayBuffer) {
      buffer = Buffer.from(data)
    } else if (ArrayBuffer.isView(data)) {
      buffer = Buffer.from(data.buffer, data.byteOffset, data.byteLength)
    }
    return originalDigest(algorithm, buffer)
  }

  Object.defineProperty(global, 'crypto', {
    value: {
      subtle: {
        ...nodeCrypto.webcrypto.subtle,
        digest: wrappedDigest,
      },
      getRandomValues: (arr) => nodeCrypto.webcrypto.getRandomValues(arr),
      randomUUID: () => nodeCrypto.randomUUID(),
    },
    writable: true,
    configurable: true,
  })
}