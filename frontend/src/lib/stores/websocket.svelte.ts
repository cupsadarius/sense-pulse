import type { AllSources, MatrixState } from '$lib/types/sources.js';

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';

const MAX_BACKOFF = 30_000;
const INITIAL_BACKOFF = 1_000;

function createWebSocketStore() {
	let connectionStatus = $state<ConnectionStatus>('disconnected');
	let sources = $state<AllSources>({});
	let matrixState = $state<MatrixState | null>(null);
	let lastUpdated = $state<number | null>(null);

	let sourcesWs: WebSocket | null = null;
	let gridWs: WebSocket | null = null;
	let sourcesBackoff = INITIAL_BACKOFF;
	let gridBackoff = INITIAL_BACKOFF;
	let sourcesReconnectTimer: ReturnType<typeof setTimeout> | null = null;
	let gridReconnectTimer: ReturnType<typeof setTimeout> | null = null;
	let intentionalClose = false;

	function getWsBaseUrl(): string {
		if (typeof window === 'undefined') return '';
		const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
		return `${proto}//${window.location.host}`;
	}

	function connectSources(): void {
		if (typeof window === 'undefined') return;
		const url = `${getWsBaseUrl()}/ws/sources`;
		connectionStatus = 'connecting';

		try {
			sourcesWs = new WebSocket(url);
		} catch {
			scheduleSourcesReconnect();
			return;
		}

		sourcesWs.onopen = () => {
			sourcesBackoff = INITIAL_BACKOFF;
			updateConnectionStatus();
		};

		sourcesWs.onmessage = (event) => {
			try {
				const data = JSON.parse(event.data) as AllSources;
				sources = data;
				lastUpdated = Date.now();
			} catch {
				// ignore malformed messages
			}
		};

		sourcesWs.onclose = () => {
			sourcesWs = null;
			updateConnectionStatus();
			if (!intentionalClose) {
				scheduleSourcesReconnect();
			}
		};

		sourcesWs.onerror = () => {
			sourcesWs?.close();
		};
	}

	function connectGrid(): void {
		if (typeof window === 'undefined') return;
		const url = `${getWsBaseUrl()}/ws/grid`;

		try {
			gridWs = new WebSocket(url);
		} catch {
			scheduleGridReconnect();
			return;
		}

		gridWs.onopen = () => {
			gridBackoff = INITIAL_BACKOFF;
		};

		gridWs.onmessage = (event) => {
			try {
				matrixState = JSON.parse(event.data) as MatrixState;
			} catch {
				// ignore malformed messages
			}
		};

		gridWs.onclose = () => {
			gridWs = null;
			if (!intentionalClose) {
				scheduleGridReconnect();
			}
		};

		gridWs.onerror = () => {
			gridWs?.close();
		};
	}

	function scheduleSourcesReconnect(): void {
		if (sourcesReconnectTimer) clearTimeout(sourcesReconnectTimer);
		sourcesReconnectTimer = setTimeout(() => {
			connectSources();
		}, sourcesBackoff);
		sourcesBackoff = Math.min(sourcesBackoff * 2, MAX_BACKOFF);
	}

	function scheduleGridReconnect(): void {
		if (gridReconnectTimer) clearTimeout(gridReconnectTimer);
		gridReconnectTimer = setTimeout(() => {
			connectGrid();
		}, gridBackoff);
		gridBackoff = Math.min(gridBackoff * 2, MAX_BACKOFF);
	}

	function updateConnectionStatus(): void {
		if (sourcesWs?.readyState === WebSocket.OPEN) {
			connectionStatus = 'connected';
		} else if (sourcesWs?.readyState === WebSocket.CONNECTING) {
			connectionStatus = 'connecting';
		} else {
			connectionStatus = 'disconnected';
		}
	}

	function connect(): void {
		intentionalClose = false;
		connectSources();
		connectGrid();
	}

	function disconnect(): void {
		intentionalClose = true;
		if (sourcesReconnectTimer) {
			clearTimeout(sourcesReconnectTimer);
			sourcesReconnectTimer = null;
		}
		if (gridReconnectTimer) {
			clearTimeout(gridReconnectTimer);
			gridReconnectTimer = null;
		}
		sourcesWs?.close();
		gridWs?.close();
		sourcesWs = null;
		gridWs = null;
		connectionStatus = 'disconnected';
	}

	return {
		get connectionStatus() {
			return connectionStatus;
		},
		get sources() {
			return sources;
		},
		get matrixState() {
			return matrixState;
		},
		get lastUpdated() {
			return lastUpdated;
		},
		connect,
		disconnect
	};
}

export const wsStore = createWebSocketStore();
