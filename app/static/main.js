function initializeStream(block) {
    const context = block.dataset.stream;
    const eventSource = new EventSource(`/stream/${context}`);
    const content = block.querySelector('.content');

    eventSource.onmessage = function(event) {
        block.querySelector('.animate-pulse')?.remove();
        const lines = event.data.split('\n');
        content.innerHTML += lines.map(line => `<span>${line}</span>`).join('<br>');
    };

    eventSource.onerror = function() {
        eventSource.close();
    };
}

document.querySelectorAll('[data-stream]').forEach(initializeStream);