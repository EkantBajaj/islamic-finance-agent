const WS_BASE_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

export class PipelineWebSocket {
    constructor(pipelineId, callbacks = {}) {
        this.pipelineId = pipelineId;
        this.url = `${WS_BASE_URL}/ws/pipeline/${pipelineId}`;
        this.callbacks = callbacks; // onMessage, onOpen, onClose, onError
        this.socket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000; // ms
        this.shouldReconnect = true;
    }

    connect() {
        try {
            this.socket = new WebSocket(this.url);

            this.socket.onopen = (event) => {
                this.reconnectAttempts = 0;
                if (this.callbacks.onOpen) this.callbacks.onOpen(event);
            };

            this.socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (this.callbacks.onMessage) this.callbacks.onMessage(data);
                } catch (e) {
                    console.error('Failed to parse WebSocket message JSON', e);
                }
            };

            this.socket.onclose = (event) => {
                if (this.callbacks.onClose) this.callbacks.onClose(event);
                if (this.shouldReconnect) {
                    this.attemptReconnect();
                }
            };

            this.socket.onerror = (error) => {
                if (this.callbacks.onError) this.callbacks.onError(error);
            };
        } catch (err) {
            console.error('Error establishing WebSocket connection', err);
            if (this.shouldReconnect) {
                this.attemptReconnect();
            }
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.warn('Max WebSocket reconnection attempts reached.');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        console.log(`Attempting WebSocket reconnect in ${delay}ms... (Attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        
        setTimeout(() => {
            if (this.shouldReconnect) {
                this.connect();
            }
        }, delay);
    }

    disconnect() {
        this.shouldReconnect = false;
        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }
    }
}
