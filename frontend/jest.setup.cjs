// jsdom doesn't provide these globals, but react-router-dom's dependency
// chain expects them to exist.
const { TextEncoder, TextDecoder } = require("node:util");
if (typeof global.TextEncoder === "undefined") {
  global.TextEncoder = TextEncoder;
}
if (typeof global.TextDecoder === "undefined") {
  global.TextDecoder = TextDecoder;
}

// jsdom doesn't implement scrollIntoView; ChatWindow calls it on every message.
if (typeof window !== "undefined") {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
}

// jest-environment-jsdom doesn't provide a global fetch; tests provide their
// own mock implementation via jest.spyOn/jest.fn.
if (typeof global.fetch === "undefined") {
  global.fetch = jest.fn();
}
