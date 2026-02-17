<script lang="ts">
	import SourceCard from './SourceCard.svelte';
	import type { Source } from '$lib/types/sources.js';

	interface Props {
		source: Source | undefined;
	}

	let { source }: Props = $props();

	let temperature = $derived(source?.readings?.temperature?.value as number | undefined);
	let humidity = $derived(source?.readings?.humidity?.value as number | undefined);
	let pressure = $derived(source?.readings?.pressure?.value as number | undefined);
</script>

<SourceCard sourceId="sensors" title="Sense HAT" icon="🌡️" {source} expectedInterval={30}>
	<div class="space-y-2">
		<div class="flex items-baseline justify-between">
			<span class="text-sm text-gray-400">Temperature</span>
			<span class="font-mono text-lg text-gray-200">
				{temperature != null ? `${(temperature as number).toFixed(1)}\u00B0C` : '—'}
			</span>
		</div>
		<div class="flex items-baseline justify-between">
			<span class="text-sm text-gray-400">Humidity</span>
			<span class="font-mono text-lg text-gray-200">
				{humidity != null ? `${(humidity as number).toFixed(1)}%` : '—'}
			</span>
		</div>
		<div class="flex items-baseline justify-between">
			<span class="text-sm text-gray-400">Pressure</span>
			<span class="font-mono text-lg text-gray-200">
				{pressure != null ? `${(pressure as number).toFixed(1)} mbar` : '—'}
			</span>
		</div>
	</div>
</SourceCard>
