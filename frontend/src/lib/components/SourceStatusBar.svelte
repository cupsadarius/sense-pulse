<script lang="ts">
	import type { AllSources, SourceAvailability } from '$lib/types/sources.js';
	import { getAvailability, EXPECTED_INTERVALS } from '$lib/utils/availability.js';

	interface Props {
		sources: AllSources;
	}

	let { sources }: Props = $props();

	const SOURCE_ORDER = ['tailscale', 'pihole', 'system', 'sensors', 'co2', 'weather', 'network_camera'];

	const LABELS: Record<string, string> = {
		tailscale: 'Tailscale',
		pihole: 'Pi-hole',
		system: 'System',
		sensors: 'Sense HAT',
		co2: 'Aranet4',
		weather: 'Weather',
		network_camera: 'Camera'
	};

	interface SourceDot {
		id: string;
		label: string;
		availability: SourceAvailability;
		hasError: boolean;
	}

	let dots = $derived.by(() => {
		const all = new Set([...SOURCE_ORDER, ...Object.keys(sources)]);
		const result: SourceDot[] = [];
		for (const id of all) {
			const source = sources[id];
			const interval = EXPECTED_INTERVALS[id] ?? 30;
			const availability = getAvailability(source, interval);
			const hasError = (source?.status?.error_count ?? 0) > 0 && availability !== 'unavailable';
			result.push({ id, label: LABELS[id] ?? id, availability, hasError });
		}
		return result;
	});

	const dotColors: Record<SourceAvailability, string> = {
		available: 'bg-status-green',
		stale: 'bg-status-yellow',
		unavailable: 'bg-status-gray'
	};

	function lastSeen(id: string): string {
		const source = sources[id];
		if (!source?.status?.last_success) return 'Never';
		const ago = Math.round(Date.now() / 1000 - source.status.last_success);
		if (ago < 60) return `${ago}s ago`;
		if (ago < 3600) return `${Math.round(ago / 60)}m ago`;
		return `${Math.round(ago / 3600)}h ago`;
	}
</script>

<div class="flex flex-wrap items-center gap-3">
	{#each dots as dot (dot.id)}
		<div class="group relative flex items-center gap-1.5" title="{dot.label}: {dot.availability} - last seen {lastSeen(dot.id)}">
			<span
				class="inline-flex h-2.5 w-2.5 rounded-full {dot.hasError ? 'bg-status-red' : dotColors[dot.availability]}"
			></span>
			<span class="text-xs text-gray-500">{dot.label}</span>
		</div>
	{/each}
</div>
