<script lang="ts">
	import type { Source } from '$lib/types/sources.js';
	import { startCamera, stopCamera } from '$lib/api/commands.js';
	import PTZControls from './PTZControls.svelte';

	interface Props {
		source: Source | undefined;
	}

	let { source }: Props = $props();

	let streamStatus = $derived((source?.readings?.stream_status?.value as string) ?? 'stopped');
	let streamError = $derived(source?.readings?.stream_error?.value as string | undefined);
	let actionPending = $state(false);
	let errorMessage = $state<string | null>(null);

	let videoEl = $state<HTMLVideoElement | null>(null);
	let hlsInstance: unknown = null;

	async function handleStart() {
		actionPending = true;
		errorMessage = null;
		try {
			const result = await startCamera();
			if (!result.success) {
				errorMessage = result.message;
			}
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : 'Failed to start camera';
		} finally {
			actionPending = false;
		}
	}

	async function handleStop() {
		actionPending = true;
		errorMessage = null;
		try {
			await stopCamera();
		} catch (e) {
			errorMessage = e instanceof Error ? e.message : 'Failed to stop camera';
		} finally {
			actionPending = false;
		}
	}

	async function initHls() {
		if (!videoEl) return;
		try {
			const Hls = (await import('hls.js')).default;
			if (Hls.isSupported()) {
				const hls = new Hls({ enableWorker: true, lowLatencyMode: true });
				hls.loadSource('/api/stream/stream.m3u8');
				hls.attachMedia(videoEl);
				hlsInstance = hls;
			} else if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {
				videoEl.src = '/api/stream/stream.m3u8';
			}
		} catch {
			errorMessage = 'Failed to load video player';
		}
	}

	function destroyHls() {
		if (hlsInstance && typeof (hlsInstance as { destroy: () => void }).destroy === 'function') {
			(hlsInstance as { destroy: () => void }).destroy();
			hlsInstance = null;
		}
	}

	$effect(() => {
		if (streamStatus === 'streaming' && videoEl) {
			initHls();
		}
		return () => {
			destroyHls();
		};
	});

	const btnClass =
		'rounded px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50';
</script>

<div class="rounded-lg border border-pulse-border bg-pulse-card p-4">
	<div class="mb-3 flex items-center justify-between">
		<div class="flex items-center gap-2">
			<span class="text-lg">📷</span>
			<h3 class="font-semibold text-gray-200">Network Camera</h3>
		</div>
		<span class="text-xs text-gray-500">{streamStatus}</span>
	</div>

	{#if streamStatus === 'stopped'}
		<div class="flex flex-col items-center gap-3 py-8">
			<p class="text-sm text-gray-400">Camera stream is stopped</p>
			<button
				class="{btnClass} bg-pulse-accent text-pulse-bg hover:bg-pulse-accent/80"
				onclick={handleStart}
				disabled={actionPending}
			>
				{actionPending ? 'Starting...' : 'Start Stream'}
			</button>
		</div>
	{:else if streamStatus === 'starting' || streamStatus === 'reconnecting'}
		<div class="flex flex-col items-center gap-3 py-8">
			<div class="h-8 w-8 animate-spin rounded-full border-2 border-pulse-accent border-t-transparent"></div>
			<p class="text-sm text-gray-400">
				{streamStatus === 'starting' ? 'Starting stream...' : 'Reconnecting...'}
			</p>
		</div>
	{:else if streamStatus === 'streaming'}
		<div class="space-y-3">
			<!-- svelte-ignore element_invalid_self_closing_tag -->
			<video
				bind:this={videoEl}
				class="w-full rounded bg-black"
				autoplay
				muted
				playsinline
			/>
			<div class="flex items-center justify-between">
				<PTZControls />
				<button
					class="{btnClass} bg-status-red/20 text-status-red hover:bg-status-red/30"
					onclick={handleStop}
					disabled={actionPending}
				>
					Stop
				</button>
			</div>
		</div>
	{:else if streamStatus === 'error'}
		<div class="flex flex-col items-center gap-3 py-8">
			<p class="text-sm text-status-red">{streamError ?? 'Stream error'}</p>
			<button
				class="{btnClass} bg-pulse-accent text-pulse-bg hover:bg-pulse-accent/80"
				onclick={handleStart}
				disabled={actionPending}
			>
				Retry
			</button>
		</div>
	{/if}

	{#if errorMessage}
		<p class="mt-2 text-xs text-status-red">{errorMessage}</p>
	{/if}
</div>
