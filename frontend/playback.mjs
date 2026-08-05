export class SegmentAudioBuffer {
  constructor(fetchSegment = globalThis.fetch.bind(globalThis)) {
    this.fetchSegment = fetchSegment;
    this.entries = new Map();
  }

  load(contractId, segIdx) {
    const key = `${contractId}:${segIdx}`;
    if (!this.entries.has(key)) {
      const request = this.fetchSegment(
        `/api/contracts/${contractId}/segments/${segIdx}`,
      ).then(async (response) => {
        if (!response.ok) {
          throw new Error(`segment ${segIdx} failed: ${response.status}`);
        }
        return response.blob();
      }).catch((error) => {
        this.entries.delete(key);
        throw error;
      });
      this.entries.set(key, request);
    }
    return this.entries.get(key);
  }

  preload(contractId, segIdx) {
    return this.load(contractId, segIdx);
  }

  clear() {
    this.entries.clear();
  }
}


export function preferredPlaybackRate(templateId) {
  return templateId === "xcash_yue" || templateId === "xcash" ? 1.1 : 1.0;
}
