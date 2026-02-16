<script lang="ts">
	import { wsStore } from '$lib/stores/websocket.svelte.js';
	import type { AllSources } from '$lib/types/sources.js';
	import TailscaleCard from '$lib/components/TailscaleCard.svelte';
	import PiholeCard from '$lib/components/PiholeCard.svelte';
	import SystemCard from '$lib/components/SystemCard.svelte';
	import SenseHatCard from '$lib/components/SenseHatCard.svelte';
	import Aranet4Card from '$lib/components/Aranet4Card.svelte';
	import WeatherCard from '$lib/components/WeatherCard.svelte';
	import LedMatrix from '$lib/components/LedMatrix.svelte';
	import NetworkCamera from '$lib/components/NetworkCamera.svelte';
	import SourceStatusBar from '$lib/components/SourceStatusBar.svelte';

	interface Props {
		data: { sources: AllSources };
	}

	let { data }: Props = $props();

	// WebSocket replaces SSR data once connected
	let sources: AllSources = $derived(
		Object.keys(wsStore.sources).length > 0 ? wsStore.sources : data.sources
	);
</script>

<div class="space-y-6">
	<!-- Source Status Bar -->
	<SourceStatusBar {sources} />

	<!-- Source Cards Grid -->
	<div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
		<TailscaleCard source={sources.tailscale} />
		<PiholeCard source={sources.pihole} />
		<SystemCard source={sources.system} />
		<SenseHatCard source={sources.sensors} />
		<Aranet4Card source={sources.co2} />
		<WeatherCard source={sources.weather} />
	</div>

	<!-- Interactive Section -->
	<div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
		<LedMatrix matrixState={wsStore.matrixState} />
		<NetworkCamera source={sources.network_camera} />
	</div>
</div>
