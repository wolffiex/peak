interface StreamBlock extends HTMLElement {
  dataset: {
    stream: string;
  };
}

globalThis.updateControl = async (entityId: string, currentState: string) => {
  try {
    const newState = currentState === "on" ? "off" : "on";
    const response = await fetch("/controls", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        entity_id: entityId,
        state: newState,
      }),
    });
    const html = await response.text();

    // Update the controls section with new state
    const controlsTarget = document.querySelector<HTMLElement>(
      "[data-controls-target]",
    );
    if (controlsTarget) {
      controlsTarget.innerHTML = html;
    }
  } catch (error) {
    console.error("Failed to update control:", error);
  }
};

async function injectControls(target: HTMLElement): Promise<void> {
  try {
    const response = await fetch("/controls");
    const html = await response.text();
    target.innerHTML = html;
  } catch (error) {
    console.error("Failed to load controls:", error);
  }
}

function initializeStream(block: StreamBlock): void {
  const context = block.dataset.stream;
  const eventSource = new EventSource(`/stream/${context}`);
  const content = block.querySelector(".content");

  if (!content) return;

  eventSource.onmessage = function (event: MessageEvent) {
    block.querySelector(".animate-pulse")?.remove();
    const lines = event.data.split("\n");
    content.innerHTML += lines
      .map((line) => `<span>${line}</span>`)
      .join("<br>");
  };

  eventSource.onerror = function () {
    eventSource.close();
  };
}

// Initialize stream-based content
document
  .querySelectorAll<StreamBlock>("[data-stream]")
  .forEach(initializeStream);

// Initialize HTML content blocks
console.log("Looking for data-html elements");
const htmlBlocks = document.querySelectorAll<HTMLElement>("[data-html]");
console.log(`Found ${htmlBlocks.length} data-html elements`);

htmlBlocks.forEach((block) => {
  const contentUrl = block.dataset.html;
  console.log(`Processing block with data-html=${contentUrl}`);
  if (!contentUrl) return;

  const content = block.querySelector(".content");
  if (!content) {
    console.log("No .content element found in the block");
    return;
  }

  console.log(`Fetching content from ${contentUrl}`);
  fetch(contentUrl)
    .then((response) => response.text())
    .then((html) => {
      console.log(`Received ${html.length} characters of HTML`);
      block.querySelector(".animate-pulse")?.remove();
      content.innerHTML = html;
    })
    .catch((error) => {
      console.error(`Failed to fetch ${contentUrl}:`, error);
      content.innerHTML = `<span>Error loading content</span>`;
    });
});

// Initialize controls
const controlsTarget = document.querySelector<HTMLElement>(
  "[data-controls-target]",
);
if (controlsTarget) {
  injectControls(controlsTarget);
}
