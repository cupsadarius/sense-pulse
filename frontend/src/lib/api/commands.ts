import { api } from './client.js';
import type { CommandResult, ConfigData, ConfigUpdateResult } from '$lib/types/sources.js';

/** Send a command to a target service */
export async function sendCommand(
	target: string,
	action: string,
	params?: Record<string, unknown>
): Promise<CommandResult> {
	return api<CommandResult>(`/api/command/${encodeURIComponent(target)}`, {
		method: 'POST',
		body: JSON.stringify({ action, ...(params ? { params } : {}) })
	});
}

/** Clear the Sense HAT LED display */
export function clearDisplay(): Promise<CommandResult> {
	return sendCommand('sensors', 'clear');
}

/** Set Sense HAT display rotation */
export function setRotation(rotation: number): Promise<CommandResult> {
	return sendCommand('sensors', 'set_rotation', { rotation });
}

/** Start the network camera stream */
export function startCamera(): Promise<CommandResult> {
	return sendCommand('orchestrator', 'start_camera');
}

/** Stop the network camera stream */
export function stopCamera(): Promise<CommandResult> {
	return sendCommand('orchestrator', 'stop_camera');
}

/** Move PTZ camera in a direction */
export function ptzMove(direction: string, step?: number): Promise<CommandResult> {
	return sendCommand('network_camera', 'ptz_move', { direction, ...(step != null ? { step } : {}) });
}

/** Trigger an ephemeral source to poll immediately */
export function triggerSource(service: string): Promise<CommandResult> {
	return sendCommand('orchestrator', 'trigger', { service });
}

/** Scan for nearby Aranet4 BLE devices */
export function scanAranet4(): Promise<CommandResult> {
	return sendCommand('orchestrator', 'scan_aranet4');
}

/** Discover RTSP cameras on the network */
export function discoverCameras(): Promise<CommandResult> {
	return sendCommand('orchestrator', 'discover_cameras');
}

/** Update config sections */
export async function updateConfig(
	sections: Partial<ConfigData>
): Promise<ConfigUpdateResult> {
	return api<ConfigUpdateResult>('/api/config', {
		method: 'POST',
		body: JSON.stringify(sections)
	});
}
