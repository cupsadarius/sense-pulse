<script lang="ts">
	import SourceCard from './SourceCard.svelte';
	import type { Source, SensorReading } from '$lib/types/sources.js';
	import { scanAranet4 } from '$lib/api/commands.js';

	interface Props {
		source: Source | undefined;
	}

	let { source }: Props = $props();

	let scanning = $state(false);
	let scanResult = $state<string | null>(null);

	interface SensorGroup {
		label: string;
		co2?: number;
		temperature?: number;
		humidity?: number;
		pressure?: number;
		battery?: number;
	}

	/** Parse flat sensor_id "{label}:{metric}" readings into grouped sensors */
	let sensors = $derived.by(() => {
		if (!source?.readings) return [];
		const groups = new Map<string, SensorGroup>();

		for (const [sensorId, reading] of Object.entries(source.readings)) {
			const parts = sensorId.split(':');
			if (parts.length !== 2) continue;
			const [label, metric] = parts;
			if (!groups.has(label)) {
				groups.set(label, { label });
			}
			const group = groups.get(label)!;
			const val = reading.value as number;
			if (metric === 'co2') group.co2 = val;
			else if (metric === 'temperature') group.temperature = val;
			else if (metric === 'humidity') group.humidity = val;
			else if (metric === 'pressure') group.pressure = val;
			else if (metric === 'battery') group.battery = val;
		}

		return Array.from(groups.values());
	});

	function co2Color(ppm: number): string {
		if (ppm >= 1200) return 'text-status-red';
		if (ppm >= 800) return 'text-status-yellow';
		return 'text-status-green';
	}

	async function handleScan() {
		scanning = true;
		scanResult = null;
		try {
			const result = await scanAranet4();
			if (result.success && result.data?.devices) {
				const devices = result.data.devices as { name: string; mac: string }[];
				scanResult = devices.length
					? devices.map((d) => `${d.name} (${d.mac})`).join(', ')
					: 'No devices found';
			} else {
				scanResult = result.message;
			}
		} catch (e) {
			scanResult = `Scan failed: ${e instanceof Error ? e.message : 'Unknown error'}`;
		} finally {
			scanning = false;
		}
	}
</script>

<SourceCard sourceId="co2" title="Aranet4 CO2" icon="💨" {source} expectedInterval={60}>
	<div class="space-y-3">
		{#each sensors as sensor (sensor.label)}
			<div class="rounded border border-pulse-border p-2">
				<div class="mb-1 text-xs font-medium text-pulse-accent">{sensor.label}</div>
				<div class="grid grid-cols-2 gap-x-4 gap-y-1">
					{#if sensor.co2 != null}
						<div class="flex items-baseline justify-between">
							<span class="text-xs text-gray-400">CO2</span>
							<span class="font-mono text-sm {co2Color(sensor.co2)}">{sensor.co2} ppm</span>
						</div>
					{/if}
					{#if sensor.temperature != null}
						<div class="flex items-baseline justify-between">
							<span class="text-xs text-gray-400">Temp</span>
							<span class="font-mono text-sm text-gray-200">{sensor.temperature.toFixed(1)}&deg;C</span>
						</div>
					{/if}
					{#if sensor.humidity != null}
						<div class="flex items-baseline justify-between">
							<span class="text-xs text-gray-400">Humidity</span>
							<span class="font-mono text-sm text-gray-200">{sensor.humidity}%</span>
						</div>
					{/if}
					{#if sensor.battery != null}
						<div class="flex items-baseline justify-between">
							<span class="text-xs text-gray-400">Battery</span>
							<span class="font-mono text-sm text-gray-200">{sensor.battery}%</span>
						</div>
					{/if}
				</div>
			</div>
		{:else}
			<p class="text-sm text-gray-500">No sensors detected</p>
		{/each}

		<button
			onclick={handleScan}
			disabled={scanning}
			class="w-full rounded border border-pulse-border px-3 py-1.5 text-xs text-gray-300 transition-colors hover:bg-pulse-border disabled:opacity-50"
		>
			{scanning ? 'Scanning...' : 'Scan for devices'}
		</button>

		{#if scanResult}
			<p class="text-xs text-gray-400">{scanResult}</p>
		{/if}
	</div>
</SourceCard>
