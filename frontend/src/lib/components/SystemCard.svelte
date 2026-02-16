<script lang="ts">
	import SourceCard from './SourceCard.svelte';
	import type { Source } from '$lib/types/sources.js';

	interface Props {
		source: Source | undefined;
	}

	let { source }: Props = $props();

	let cpu = $derived(source?.readings?.cpu_percent?.value as number | undefined);
	let memory = $derived(source?.readings?.memory_percent?.value as number | undefined);
	let load = $derived(source?.readings?.load_1min?.value as number | undefined);
	let temp = $derived(source?.readings?.cpu_temp?.value as number | undefined);

	function tempColor(t: number): string {
		if (t >= 80) return 'text-status-red';
		if (t >= 60) return 'text-status-yellow';
		return 'text-status-green';
	}

	function usageColor(pct: number): string {
		if (pct >= 90) return 'bg-status-red';
		if (pct >= 70) return 'bg-status-yellow';
		return 'bg-pulse-accent';
	}
</script>

<SourceCard sourceId="system" title="System" icon="🖥️" {source} expectedInterval={30}>
	<div class="space-y-3">
		{#if cpu != null}
			<div>
				<div class="mb-1 flex items-baseline justify-between">
					<span class="text-sm text-gray-400">CPU</span>
					<span class="font-mono text-sm text-gray-300">{cpu.toFixed(1)}%</span>
				</div>
				<div class="h-2 w-full overflow-hidden rounded-full bg-pulse-border">
					<div
						class="h-full rounded-full transition-all duration-500 {usageColor(cpu)}"
						style="width: {Math.min(cpu, 100)}%"
					></div>
				</div>
			</div>
		{/if}
		{#if memory != null}
			<div>
				<div class="mb-1 flex items-baseline justify-between">
					<span class="text-sm text-gray-400">Memory</span>
					<span class="font-mono text-sm text-gray-300">{memory.toFixed(1)}%</span>
				</div>
				<div class="h-2 w-full overflow-hidden rounded-full bg-pulse-border">
					<div
						class="h-full rounded-full transition-all duration-500 {usageColor(memory)}"
						style="width: {Math.min(memory, 100)}%"
					></div>
				</div>
			</div>
		{/if}
		<div class="flex items-baseline justify-between">
			<span class="text-sm text-gray-400">Load (1m)</span>
			<span class="font-mono text-lg text-gray-200">{load?.toFixed(2) ?? '—'}</span>
		</div>
		{#if temp != null}
			<div class="flex items-baseline justify-between">
				<span class="text-sm text-gray-400">CPU Temp</span>
				<span class="font-mono text-lg {tempColor(temp)}">{temp.toFixed(1)}&deg;C</span>
			</div>
		{/if}
	</div>
</SourceCard>
