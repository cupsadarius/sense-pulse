<script lang="ts">
	import { ptzMove } from '$lib/api/commands.js';

	let moving = $state<string | null>(null);

	async function move(direction: string) {
		moving = direction;
		try {
			await ptzMove(direction);
		} catch {
			// silently fail, camera card handles errors
		} finally {
			moving = null;
		}
	}

	const btnClass =
		'flex h-9 w-9 items-center justify-center rounded bg-pulse-border text-gray-300 transition-colors hover:bg-pulse-accent/30 disabled:opacity-30';
</script>

<div class="inline-grid grid-cols-3 grid-rows-3 gap-1">
	<div></div>
	<button class={btnClass} onclick={() => move('up')} disabled={moving !== null} aria-label="Pan up">
		&#9650;
	</button>
	<div></div>

	<button class={btnClass} onclick={() => move('left')} disabled={moving !== null} aria-label="Pan left">
		&#9664;
	</button>
	<div class="flex h-9 w-9 items-center justify-center text-xs text-gray-500">PTZ</div>
	<button class={btnClass} onclick={() => move('right')} disabled={moving !== null} aria-label="Pan right">
		&#9654;
	</button>

	<button class={btnClass} onclick={() => move('zoom_in')} disabled={moving !== null} aria-label="Zoom in">
		+
	</button>
	<button class={btnClass} onclick={() => move('down')} disabled={moving !== null} aria-label="Pan down">
		&#9660;
	</button>
	<button class={btnClass} onclick={() => move('zoom_out')} disabled={moving !== null} aria-label="Zoom out">
		&minus;
	</button>
</div>
