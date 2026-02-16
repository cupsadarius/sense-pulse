<script lang="ts">
	interface Props {
		status: 'connecting' | 'connected' | 'disconnected';
	}

	let { status }: Props = $props();

	const colors: Record<string, string> = {
		connected: 'bg-status-green',
		connecting: 'bg-status-yellow',
		disconnected: 'bg-status-red'
	};

	const labels: Record<string, string> = {
		connected: 'Connected',
		connecting: 'Connecting...',
		disconnected: 'Disconnected'
	};
</script>

<div class="flex items-center gap-2 text-sm">
	<span class="relative flex h-2.5 w-2.5">
		{#if status === 'connecting'}
			<span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-status-yellow opacity-75"></span>
		{/if}
		<span class="relative inline-flex h-2.5 w-2.5 rounded-full {colors[status]}"></span>
	</span>
	<span class="text-gray-400">{labels[status]}</span>
</div>
