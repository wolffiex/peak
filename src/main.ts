interface StreamBlock extends HTMLElement {
    dataset: {
        stream: string;
    };
}

async function updateControl(entityId: string, newState: string): Promise<void> {
    try {
        const response = await fetch('/controls', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                entity_id: entityId,
                state: newState
            })
        });
        const html = await response.text();
        
        // Update the controls section with new state
        const controlsTarget = document.querySelector<HTMLElement>('[data-controls-target]');
        if (controlsTarget) {
            controlsTarget.innerHTML = html;
            initializeControlHandlers();
        }
    } catch (error) {
        console.error('Failed to update control:', error);
    }
}

function initializeControlHandlers(): void {
    document.querySelectorAll<HTMLButtonElement>('[data-entity-id]').forEach(button => {
        button.addEventListener('click', () => {
            const entityId = button.dataset.entityId;
            if (!entityId) return;
            
            // Set the new state based on current aria-checked value
            const newState = button.getAttribute('aria-checked') === 'true' ? 'off' : 'on';
            updateControl(entityId, newState);
        });
    });
}

async function injectControls(target: HTMLElement): Promise<void> {
    try {
        const response = await fetch('/controls');
        const html = await response.text();
        target.innerHTML = html;
        initializeControlHandlers();
    } catch (error) {
        console.error('Failed to load controls:', error);
    }
}

function initializeStream(block: StreamBlock): void {
    const context = block.dataset.stream;
  return
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

const controlsTarget = document.querySelector<HTMLElement>('[data-controls-target]');
if (controlsTarget) {
    injectControls(controlsTarget);
}
