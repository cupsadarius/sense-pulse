import type { Source, SourceAvailability } from '$lib/types/sources.js';

/** Expected poll intervals per source (seconds) */
export const EXPECTED_INTERVALS: Record<string, number> = {
	tailscale: 30,
	pihole: 30,
	system: 30,
	sensors: 30,
	co2: 60,
	weather: 300,
	network_camera: 30
};

/** Determine availability state of a source */
export function getAvailability(
	source: Source | undefined,
	expectedInterval: number
): SourceAvailability {
	if (!source || !source.status) return 'unavailable';
	if (Object.keys(source.readings).length === 0) return 'unavailable';
	const latest = source.status.last_success;
	if (!latest) return 'unavailable';
	const ageSeconds = Date.now() / 1000 - latest;
	if (ageSeconds > expectedInterval * 3) return 'stale';
	return 'available';
}
