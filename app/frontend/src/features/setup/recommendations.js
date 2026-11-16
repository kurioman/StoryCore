// First-run assistant (v1.8): model advice. Sizes are the GGUF files of TheDrummer/Rocinante-12B-v1.1 (Hugging Face);
// the video memory also has to hold the story context (about 2.5 GB for 16k tokens on this model), hence the margins.
import { msg } from "@/i18n";

export const ROCINANTE = {
  name: `Rocinante 12B v1.1`,
  author: `TheDrummer`,
  search: `Rocinante-12B-v1.1`,
  page: `https://huggingface.co/TheDrummer/Rocinante-12B-v1.1-GGUF`,
};

export const VRAM_CHOICES = [4, 6, 8, 10, 12, 16, 24];

/** The Rocinante file to download for a given video memory (GB). */
export function rocinanteFor(vram) {
  if (vram >= 20) return { quant: `Q8_0`, size: 13.0, context: 16384, fits: true };
  if (vram >= 16) return { quant: `Q6_K`, size: 10.1, context: 16384, fits: true };
  if (vram >= 12) return { quant: `Q5_K_M`, size: 8.7, context: 16384, fits: true, lighter: `Q4_K_M` };
  if (vram >= 10) return { quant: `Q4_K_M`, size: 7.5, context: 12288, fits: true };
  if (vram >= 8) return { quant: `IQ4_XS`, size: 6.8, context: 8192, fits: true, lighter: `Q3_K_M` };
  return { quant: `Q3_K_M`, size: 6.1, context: 8192, fits: false };
}

// Getters: the texts are read at render time, after the language is chosen.
export const CLOUD_MODELS = [
  {
    id: `claude`,
    name: `Claude`,
    maker: `Anthropic`,
    search: `Claude Sonnet`,
    get pros() { return msg("The best writing quality: rich, coherent, respects the characters.", {}); },
    get cons() { return msg("Clearly the most expensive. Opus costs even more than Sonnet.", {}); },
    cost: 3,
  },
  {
    id: `deepseek`,
    name: `DeepSeek`,
    maker: `DeepSeek`,
    search: `DeepSeek`,
    get pros() { return msg("Very cheap, good at long stories.", {}); },
    get cons() { return msg("A less refined style than Claude.", {}); },
    cost: 1,
  },
  {
    id: `gemini`,
    name: `Gemini`,
    maker: `Google`,
    search: `Gemini Flash`,
    get pros() { return msg("Fast and cheap; Flash models have a limited free tier on Google's own site.", {}); },
    get cons() { return msg("Can refuse or soften some dark scenes.", {}); },
    cost: 1,
  },
  {
    id: `mistral`,
    name: `Mistral`,
    maker: `Mistral AI (France)`,
    search: `Mistral Medium`,
    get pros() { return msg("Made in France: natural French, a good choice to play in French.", {}); },
    get cons() { return msg("Mid-range price; a little less creative than Claude.", {}); },
    cost: 2,
  },
];
