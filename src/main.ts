interface StreamBlock extends HTMLElement {
    dataset: {
        stream: string;
    };
}

function initializeStream(block: StreamBlock): void {
    const context = block.dataset.stream;
    const eventSource = new EventSource(`/stream/${context}`);
    const content = block.querySelector('.content');

    if (!content) return;

    eventSource.onmessage = function(event: MessageEvent) {
        block.querySelector('.animate-pulse')?.remove();
        const lines = event.data.split('\n');
        content.innerHTML += lines.map(line => `<span>${line}</span>`).join('<br>');
    };

    eventSource.onerror = function() {
        eventSource.close();
    };
}

document.querySelectorAll<StreamBlock>('[data-stream]').forEach(initializeStream);