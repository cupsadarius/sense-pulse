<script lang="ts">
	import SourceCard from './SourceCard.svelte';
	import type { Source } from '$lib/types/sources.js';

	interface Props {
		source: Source | undefined;
	}

	let { source }: Props = $props();

	let queries = $derived(source?.readings?.queries_today?.value as number | undefined);
	let blocked = $derived(source?.readings?.ads_blocked_today?.value as number | undefined);
	let percentage = $derived(source?.readings?.ads_percentage_today?.value as number | undefined);
</script>

<SourceCard sourceId="pihole" title="Pi-hole" icon="🛡️" {source} expectedInterval={30}>
	<div class="space-y-3">
		<div class="flex items-baseline justify-between">
			<span class="text-sm text-gray-400">Queries</span>
			<span class="font-mono text-xl text-gray-200">{queries?.toLocaleString() ?? '—'}</span>
		</div>
		<div class="flex items-baseline justify-between">
			<span class="text-sm text-gray-400">Blocked</span>
			<span class="font-mono text-xl text-gray-200">{blocked?.toLocaleString() ?? '—'}</span>
		</div>
		{#if percentage != null}
			<div>
				<div class="mb-1 flex items-baseline justify-between">
					<span class="text-sm text-gray-400">Block rate</span>
					<span class="font-mono text-sm text-gray-300">{percentage.toFixed(1)}%</span>
				</div>
				<div class="h-2 w-full overflow-hidden rounded-full bg-pulse-border">
					<div
						class="h-full rounded-full bg-pulse-accent transition-all duration-500"
						style="width: {Math.min(percentage, 100)}%"
					></div>
				</div>
			</div>
		{/if}
	</div>
</SourceCard>
