<script lang="ts">
	import type { MatrixState } from '$lib/types/sources.js';

	interface Props {
		matrixState: MatrixState | null;
	}

	let { matrixState }: Props = $props();

	let pixels = $derived(matrixState?.pixels ?? []);
	let available = $derived(matrixState?.available ?? false);
	let mode = $derived(matrixState?.mode ?? 'unknown');

	function pixelColor(pixel: number[]): string {
		if (!pixel || pixel.length < 3) return 'rgb(0,0,0)';
		return `rgb(${pixel[0]},${pixel[1]},${pixel[2]})`;
	}
</script>

<div class="rounded-lg border border-pulse-border bg-pulse-card p-4">
	<div class="mb-3 flex items-center justify-between">
		<div class="flex items-center gap-2">
			<span class="text-lg">💡</span>
			<h3 class="font-semibold text-gray-200">LED Matrix</h3>
		</div>
		{#if available}
			<span class="text-xs text-gray-500">{mode}</span>
		{/if}
	</div>

	{#if !available}
		<div class="flex aspect-square items-center justify-center rounded bg-pulse-bg">
			<span class="text-sm text-status-gray">Sense HAT unavailable</span>
		</div>
	{:else}
		<div class="mx-auto grid aspect-square max-w-48 grid-cols-8 grid-rows-8 gap-0.5 rounded bg-pulse-bg p-1">
			{#each { length: 64 } as _, i}
				<div
					class="aspect-square rounded-sm transition-colors duration-150"
					style="background-color: {pixelColor(pixels[i])}"
				></div>
			{/each}
		</div>
	{/if}
</div>
