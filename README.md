# MetaFusion: Distributed Metadata and Vector Fusion Store

## Run with Command Line

To initialize a leader node:

```shell
python -m meta_fusion.main leader --host <leader_host> --port<leader_port> --index_path <index_path> --model_name <model_name> --device <device> --normalize <normalize>
```

or use the default setting:

```shell
python -m meta_fusion.main leader
```

To initialize a follower node:

```shell
python -m meta_fusion.main follower --host <follower_host> --port <follower_port> --leader_host <leader_host> --leader_port <leader_port>
```

