/** A single sensor reading: always scalar value + unit + timestamp */
export interface SensorReading {
	value: number | string | boolean;
	unit: string | null;
	timestamp: number;
}

/** All readings for a source, keyed by sensor_id */
export interface SourceReadings {
	[sensorId: string]: SensorReading;
}

/** Source health/poll status from the orchestrator */
export interface SourceStatus {
	last_poll: number | null;
	last_success: number | null;
	last_error: string | null;
	poll_count: number;
	error_count: number;
}

/** A single source: readings + status merged */
export interface Source {
	readings: SourceReadings;
	status: SourceStatus | null;
}

/** All sources keyed by source_id */
export interface AllSources {
	[sourceId: string]: Source;
}

/** Response from POST /api/command/{target} */
export interface CommandResult {
	success: boolean;
	message: string;
	data?: Record<string, unknown>;
}

/** LED matrix state from WS /ws/grid */
export interface MatrixState {
	pixels: number[][]; // 64 elements of [r,g,b]
	mode: string;
	rotation: number;
	available: boolean;
}

/** Visual availability state for a source */
export type SourceAvailability = 'available' | 'stale' | 'unavailable';

/** Config data from GET /api/config */
export interface ConfigData {
	display?: { rotation?: number; scroll_speed?: number; icon_duration?: number };
	sleep?: { start_hour?: number; end_hour?: number; disable_pi_leds?: boolean };
	schedule?: Record<string, number>;
	weather?: { location?: string };
	pihole?: { host?: string; password?: string };
	aranet4?: { sensors?: { label: string; mac: string }[]; timeout?: number };
	camera?: { cameras?: unknown[] };
	auth?: { enabled?: boolean; username?: string };
	[key: string]: unknown;
}

/** Config update response */
export interface ConfigUpdateResult {
	status: string;
	sections_updated: string[];
}
