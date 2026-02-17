<script lang="ts">
	import '../app.css';
	import ConnectionStatus from '$lib/components/ConnectionStatus.svelte';
	import { wsStore } from '$lib/stores/websocket.svelte.js';
	import { onMount } from 'svelte';
	import type { Snippet } from 'svelte';

	interface Props {
		children: Snippet;
	}

	let { children }: Props = $props();

	let lastUpdatedStr = $derived(
		wsStore.lastUpdated ? new Date(wsStore.lastUpdated).toLocaleTimeString() : '—'
	);

	onMount(() => {
		wsStore.connect();
		return () => wsStore.disconnect();
	});
</script>

<div class="min-h-screen bg-pulse-bg text-gray-200">
	<header class="border-b border-pulse-border bg-pulse-card">
		<div class="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
			<div class="flex items-center gap-3">
				<h1 class="text-lg font-bold text-pulse-accent">Sense Pulse</h1>
			</div>
			<div class="flex items-center gap-4">
				<span class="text-xs text-gray-500">Updated {lastUpdatedStr}</span>
				<ConnectionStatus status={wsStore.connectionStatus} />
			</div>
		</div>
	</header>

	<main class="mx-auto max-w-7xl px-4 py-6">
		{@render children()}
	</main>
</div>
