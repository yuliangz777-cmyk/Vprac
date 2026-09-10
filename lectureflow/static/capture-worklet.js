// Runs on the audio thread: batches the 128-sample render quantum into
// larger blocks and ships them to the main thread. Capture never stops, so
// there is no gap in the recording while a chunk is being transcribed.
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.block = new Float32Array(1024);
    this.filled = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    for (let i = 0; i < channel.length; i++) {
      this.block[this.filled++] = channel[i];
      if (this.filled === this.block.length) {
        const out = this.block.slice(0);
        this.port.postMessage(out, [out.buffer]);
        this.filled = 0;
      }
    }
    return true;
  }
}

registerProcessor('lectureflow-capture', CaptureProcessor);
