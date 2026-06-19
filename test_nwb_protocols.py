import h5py

filepath = "./paper/allen_cache/cell_480087928.nwb"
with h5py.File(filepath, 'r') as f:
    if 'stimulus/presentation' in f:
        stim_group = f['stimulus/presentation']
        keys = list(stim_group.keys())
        print(f"Total sweeps in stimulus/presentation: {len(keys)}")
        
        # Sample sweep attrs
        for sweep_id in keys[:5]:
            print(f"\nSweep {sweep_id} attrs:")
            for k, v in stim_group[sweep_id].attrs.items():
                print(f"  {k}: {v}")
    else:
        print("No stimulus/presentation")

    if 'epochs' in f:
        print("\nFound epochs:")
        ep_group = f['epochs']
        for ep in list(ep_group.keys())[:5]:
            print(f" Epoch {ep}:")
            for k, v in ep_group[ep].attrs.items():
                print(f"  {k}: {v}")
            if 'description' in ep_group[ep]:
                print(f"  description: {ep_group[ep]['description'][()]}")
            if 'timeseries' in ep_group[ep]:
                print(f"  timeseries links: {list(ep_group[ep]['timeseries'].keys())}")
    
