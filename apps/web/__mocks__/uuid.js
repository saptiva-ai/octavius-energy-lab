// Mock for uuid module (ESM compatibility with Jest)
let uuidCounter = 0;

module.exports = {
  v4: jest.fn(() => `mock-uuid-v4-${++uuidCounter}`),
  v1: jest.fn(() => `mock-uuid-v1-${++uuidCounter}`),
  v3: jest.fn(() => `mock-uuid-v3-${++uuidCounter}`),
  v5: jest.fn(() => `mock-uuid-v5-${++uuidCounter}`),
  NIL: '00000000-0000-0000-0000-000000000000',
  MAX: 'ffffffff-ffff-ffff-ffff-ffffffffffff',
  validate: jest.fn(() => true),
  version: jest.fn(() => 4),
  parse: jest.fn(),
  stringify: jest.fn(),
};
