import { toBlob } from "html-to-image";

type SavePickerWindow = Window & {
  showSaveFilePicker?: (options?: {
    suggestedName?: string;
    types?: Array<{
      description?: string;
      accept: Record<string, string[]>;
    }>;
  }) => Promise<{
    createWritable: () => Promise<{
      write: (data: Blob) => Promise<void>;
      close: () => Promise<void>;
    }>;
  }>;
};

/** Swap header inputs for text nodes so values appear in the PNG. */
function prepareHeaderInputs(root: HTMLElement): () => void {
  const restores: Array<() => void> = [];
  root
    .querySelectorAll<HTMLInputElement>("input.radar-layout-header-input")
    .forEach((input) => {
      const text = document.createElement("div");
      text.className = "radar-layout-header-text";
      text.textContent = input.value.trim() ? input.value : "\u00a0";
      input.style.display = "none";
      input.parentElement?.insertBefore(text, input);
      restores.push(() => {
        text.remove();
        input.style.display = "";
      });
    });
  return () => {
    for (const restore of restores) restore();
  };
}

async function savePngBlob(blob: Blob, suggestedName: string): Promise<void> {
  const w = window as SavePickerWindow;
  if (typeof w.showSaveFilePicker === "function") {
    try {
      const handle = await w.showSaveFilePicker({
        suggestedName,
        types: [
          {
            description: "PNG image",
            accept: { "image/png": [".png"] },
          },
        ],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    } catch (err) {
      // User cancelled the picker — not an error.
      if (err instanceof DOMException && err.name === "AbortError") return;
      throw err;
    }
  }

  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = suggestedName;
    a.click();
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * Capture `element` at browser display size (CSS pixels, pixelRatio 1)
 * without clipping overflow, then save via file picker (or download fallback).
 */
export async function exportElementAsPng(
  element: HTMLElement,
  suggestedName: string,
): Promise<void> {
  const restoreInputs = prepareHeaderInputs(element);
  const prevMaxWidth = element.style.maxWidth;
  const prevOverflow = element.style.overflow;
  const prevWidth = element.style.width;
  const prevHeight = element.style.height;

  try {
    // Expand so scroll* matches full content (no clipped edges).
    element.style.maxWidth = "none";
    element.style.overflow = "visible";
    element.style.width = "max-content";
    element.style.height = "max-content";

    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => resolve());
    });

    const width = Math.ceil(element.scrollWidth);
    const height = Math.ceil(element.scrollHeight);
    if (width <= 0 || height <= 0) {
      throw new Error("キャプチャ対象のサイズが取得できません");
    }

    const blob = await toBlob(element, {
      cacheBust: true,
      pixelRatio: 1,
      width,
      height,
      canvasWidth: width,
      canvasHeight: height,
      style: {
        maxWidth: "none",
        overflow: "visible",
        width: `${width}px`,
        height: `${height}px`,
        transform: "none",
        margin: "0",
      },
      filter: (node) => {
        if (!(node instanceof HTMLElement)) return true;
        return !node.classList.contains("radar-layout-handle");
      },
    });

    if (!blob) throw new Error("PNG の生成に失敗しました");
    await savePngBlob(blob, suggestedName);
  } finally {
    element.style.maxWidth = prevMaxWidth;
    element.style.overflow = prevOverflow;
    element.style.width = prevWidth;
    element.style.height = prevHeight;
    restoreInputs();
  }
}

export function defaultObsPngName(): string {
  const stamp = new Date()
    .toISOString()
    .slice(0, 19)
    .replace(/[:T]/g, (ch) => (ch === "T" ? "_" : ch === ":" ? "" : "-"));
  return `pentaklip-obs-${stamp}.png`;
}
