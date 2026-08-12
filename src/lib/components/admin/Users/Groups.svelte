<script lang="ts">
	import { getContext, onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { toast } from 'svelte-sonner';

	import { user } from '$lib/stores';
	import { createNewGroup, getGroups } from '$lib/apis/groups';
	import { getUserDefaultPermissions, updateUserDefaultPermissions } from '$lib/apis/users';

	import AddGroupModal from './Groups/AddGroupModal.svelte';
	import GroupItem from './Groups/GroupItem.svelte';
	import GroupModal from './Groups/EditGroupModal.svelte';
	import HaloSelect from '$lib/components/common/HaloSelect.svelte';
	import MagnifyingGlass from '$lib/components/icons/MagnifyingGlass.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import UsersSolid from '$lib/components/icons/UsersSolid.svelte';
	import WrenchSolid from '$lib/components/icons/WrenchSolid.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	const i18n = getContext('i18n');

	export let users: any[] = [];
	export let setGroupCount: (count: number) => void = () => {};
	export let setPermissionCount: (count: number) => void = () => {};

	let loaded = false;

	let groups: any[] = [];
	let search = '';
	let sortBy = 'name-asc';
	let showCreateGroupModal = false;
	let showDefaultPermissionsModal = false;

	let defaultPermissions = {
		workspace: {
			models: false,
			knowledge: false,
			prompts: false,
			tools: false
		},
		sharing: {
			public_models: false,
			public_knowledge: false,
			public_prompts: false,
			public_tools: false
		},
		chat: {
			controls: true,
			file_upload: true,
			delete: true,
			edit: true,
			stt: true,
			tts: true,
			call: true,
			multiple_models: true,
			temporary: true,
			temporary_enforced: false
		},
		features: {
			direct_tool_servers: false,
			web_search: true,
			image_generation: true,
			video_generation: false,
			code_interpreter: true
		}
	};

	const countEnabled = (target: Record<string, any>) =>
		Object.values(target ?? {}).reduce((sum, value) => {
			if (typeof value === 'boolean') {
				return sum + (value ? 1 : 0);
			}

			if (value && typeof value === 'object') {
				return sum + countEnabled(value as Record<string, any>);
			}

			return sum;
		}, 0);

	const setGroups = async () => {
		groups = await getGroups(localStorage.token);
		setGroupCount(groups.length);
	};

	const addGroupHandler = async (group: any) => {
		const res = await createNewGroup(localStorage.token, group).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Group created successfully'));
			await setGroups();
		}
	};

	const updateDefaultPermissionsHandler = async (group: any) => {
		const res = await updateUserDefaultPermissions(localStorage.token, group.permissions).catch(
			(error) => {
				toast.error(`${error}`);
				return null;
			}
		);

		if (res) {
			toast.success($i18n.t('Default permissions updated successfully'));
			defaultPermissions = await getUserDefaultPermissions(localStorage.token);
		}
	};

	$: filteredGroups = groups
		.filter((group) => {
			if (!search.trim()) return true;
			return (group?.name ?? '').toLowerCase().includes(search.toLowerCase());
		})
		.sort((a, b) => {
			switch (sortBy) {
				case 'name-desc':
					return b.name.localeCompare(a.name);
				case 'members-desc':
					return b.user_ids.length - a.user_ids.length;
				case 'members-asc':
					return a.user_ids.length - b.user_ids.length;
				case 'newest':
					return b.created_at - a.created_at;
				case 'oldest':
					return a.created_at - b.created_at;
				default:
					return a.name.localeCompare(b.name);
			}
		});
	$: totalPermissions = countEnabled(defaultPermissions);
	$: setPermissionCount(totalPermissions);
	$: permissionSummary = [
		{ label: $i18n.t('Permissions'), value: totalPermissions },
		{ label: $i18n.t('Workspace'), value: countEnabled(defaultPermissions.workspace) },
		{ label: $i18n.t('Chat'), value: countEnabled(defaultPermissions.chat) },
		{ label: $i18n.t('Features'), value: countEnabled(defaultPermissions.features) }
	];

	onMount(async () => {
		if ($user?.role !== 'admin') {
			await goto('/');
			return;
		}

		await setGroups();
		defaultPermissions = await getUserDefaultPermissions(localStorage.token);
		loaded = true;
	});
</script>

{#if loaded}
	<AddGroupModal bind:show={showCreateGroupModal} onSubmit={addGroupHandler} />

	<GroupModal
		bind:show={showDefaultPermissionsModal}
		tabs={['permissions']}
		bind:permissions={defaultPermissions}
		custom={false}
		onSubmit={updateDefaultPermissionsHandler}
	/>

	<div class="space-y-6">
		<!-- Groups section: Toolbar + List -->
		<section class="glass-section p-5 space-y-5">
			<div class="flex items-center gap-3">
				<div class="glass-icon-badge bg-violet-50 dark:bg-violet-950/30">
					<UsersSolid className="size-[18px] text-violet-500 dark:text-violet-400" />
				</div>
				<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
					{$i18n.t('Groups')}
				</div>
			</div>

			<!-- Toolbar: Search + Sort + Create -->
			<div class="flex flex-wrap items-center gap-3">
				<div class="glass-item px-4 py-2.5 flex min-w-0 flex-1 items-center gap-3">
					<div class="text-gray-400 dark:text-gray-500">
						<MagnifyingGlass className="size-4" />
					</div>
					<input
						class="w-full bg-transparent text-sm text-gray-800 outline-hidden placeholder:text-gray-400 dark:text-gray-100 dark:placeholder:text-gray-500"
						bind:value={search}
						placeholder={$i18n.t('Search groups')}
					/>
					{#if search.trim()}
						<button
							type="button"
							class="rounded-lg p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-200"
							on:click={() => {
								search = '';
							}}
						>
							<XMark className="size-4" />
						</button>
					{/if}
				</div>

				<HaloSelect
					bind:value={sortBy}
					options={[
						{ value: 'name-asc', label: `${$i18n.t('Name')} (A-Z)` },
						{ value: 'name-desc', label: `${$i18n.t('Name')} (Z-A)` },
						{ value: 'members-desc', label: $i18n.t('Most members') },
						{ value: 'members-asc', label: $i18n.t('Fewest members') },
						{ value: 'newest', label: $i18n.t('Newest first') },
						{ value: 'oldest', label: $i18n.t('Oldest first') }
					]}
				/>

				<button
					type="button"
					class="inline-flex shrink-0 items-center gap-2 rounded-xl bg-gray-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-gray-800 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-100"
					on:click={() => {
						showCreateGroupModal = true;
					}}
				>
					<Plus className="size-4" />
					<span>{$i18n.t('Create Group')}</span>
				</button>
			</div>

			<!-- Group list or empty state -->
			{#if filteredGroups.length === 0}
				<div class="px-2 py-10 text-center">
					<div class="glass-icon-badge bg-gray-100 dark:bg-gray-800 mx-auto">
						<UsersSolid className="size-[18px] text-gray-500 dark:text-gray-400" />
					</div>
					<div class="mt-3 text-sm font-medium text-gray-500 dark:text-gray-400">
						{search.trim() ? $i18n.t('No groups found') : $i18n.t('Organize your users')}
					</div>
					<div class="mx-auto mt-1.5 max-w-md text-xs text-gray-400 dark:text-gray-500">
						{#if search.trim()}
							{$i18n.t('Try adjusting your search or create a new group.')}
						{:else}
							{$i18n.t('Use groups to group your users and assign permissions.')}
						{/if}
					</div>
				</div>
			{:else}
				<div class="grid gap-3 lg:grid-cols-2">
					{#each filteredGroups as group (group.id)}
						<GroupItem {group} {users} {setGroups} />
					{/each}
				</div>
			{/if}
		</section>

		<!-- Default Permissions Section -->
		<section class="glass-section p-5 space-y-5">
			<div class="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
				<div class="flex items-start gap-3">
					<div class="glass-icon-badge bg-amber-50 dark:bg-amber-950/30">
						<WrenchSolid className="size-[18px] text-amber-500 dark:text-amber-400" />
					</div>
					<div>
						<div class="text-base font-semibold text-gray-800 dark:text-gray-100">
							{$i18n.t('Default permissions')}
						</div>
						<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">
							{$i18n.t('applies to all users with the "user" role')}
						</div>
					</div>
				</div>

				<button
					type="button"
					class="glass-item px-4 py-3 inline-flex items-center gap-2 text-sm font-medium transition hover:bg-white dark:hover:bg-gray-900/70"
					on:click={() => {
						showDefaultPermissionsModal = true;
					}}
				>
					<span>{$i18n.t('Edit Default Permissions')}</span>
				</button>
			</div>

			<div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
				{#each permissionSummary as item}
					<div class="glass-item p-4">
						<div class="text-xs font-medium text-gray-500 dark:text-gray-400">
							{item.label}
						</div>
						<div class="mt-2 text-2xl font-semibold tracking-tight text-gray-900 dark:text-white">
							{item.value}
						</div>
					</div>
				{/each}
			</div>
		</section>
	</div>
{/if}
