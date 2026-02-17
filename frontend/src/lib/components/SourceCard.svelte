<script lang="ts">
	import type { Source, SourceAvailability } from '$lib/types/sources.js';
	import { getAvailability } from '$lib/utils/availability.js';
	import type { Snippet } from 'svelte';

	interface Props {
		sourceId: string;
		title: string;
		icon: string;
		source: Source | undefined;
		expectedInterval: number;
		children?: Snippet;
	}

	let { sourceId, title, icon, source, expectedInterval, children }: Props = $props();

	let availability: SourceAvailability = $derived(getAvailability(source, expectedInterval));

	const borderColors: Record<SourceAvailability, string> = {
		available: 'border-pulse-border',
		stale: 'border-status-yellow',
		unavailable: 'border-pulse-border'
	};

	const dotColors: Record<SourceAvailability, string> = {
		available: 'bg-status-green',
		stale: 'bg-status-yellow',
		unavailable: 'bg-status-gray'
	};
</script>

<div
	class="rounded-lg border bg-pulse-card p-4 transition-all duration-300 {borderColors[availability]} {availability === 'unavailable' ? 'opacity-50' : ''}"
>
	<div class="mb-3 flex items-center justify-between">
		<div class="flex items-center gap-2">
			<span class="text-lg">{icon}</span>
			<h3 class="font-semibold text-gray-200">{title}</h3>
		</div>
		<span class="inline-flex h-2.5 w-2.5 rounded-full {dotColors[availability]}" title="{sourceId}: {availability}"></span>
	</div>

	{#if availability === 'stale'}
		<div class="mb-2 rounded bg-status-yellow/10 px-2 py-1 text-xs text-status-yellow">
			Data may be outdated
		</div>
	{/if}

	{#if availability === 'unavailable'}
		<p class="text-sm text-status-gray">Source offline</p>
	{:else if children}
		{@render children()}
	{/if}
</div>
