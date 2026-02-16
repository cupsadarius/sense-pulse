<script lang="ts">
	import SourceCard from './SourceCard.svelte';
	import type { Source } from '$lib/types/sources.js';

	interface Props {
		source: Source | undefined;
	}

	let { source }: Props = $props();

	let connected = $derived(source?.readings?.connected?.value as boolean | undefined);
	let deviceCount = $derived(source?.readings?.device_count?.value as number | undefined);
</script>

<SourceCard sourceId="tailscale" title="Tailscale" icon="🔗" {source} expectedInterval={30}>
	<div class="space-y-2">
		<div class="flex items-center gap-2">
			<span
				class="rounded px-2 py-0.5 text-xs font-medium {connected
					? 'bg-status-green/20 text-status-green'
					: 'bg-status-red/20 text-status-red'}"
			>
				{connected ? 'Connected' : 'Disconnected'}
			</span>
		</div>
		{#if deviceCount != null}
			<div class="flex items-baseline justify-between">
				<span class="text-sm text-gray-400">Peers</span>
				<span class="font-mono text-xl text-gray-200">{deviceCount}</span>
			</div>
		{/if}
	</div>
</SourceCard>
