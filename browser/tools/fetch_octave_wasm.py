import asyncio, sys, rattler, pickle
from rattler import Channel
async def main(specs):
    ch=[Channel("https://prefix.dev/emscripten-forge-4x"),Channel("https://prefix.dev/conda-forge")]
    recs = await rattler.solve(sources=ch, specs=specs, platforms=["emscripten-wasm32","noarch"],
        virtual_packages=[rattler.GenericVirtualPackage(rattler.PackageName("__emscripten"), rattler.Version("4.0.9"), rattler.package.build_string.BuildString("0"))])
    tot=0
    for r in sorted(recs, key=lambda r:-(r.size or 0)):
        tot+=r.size or 0
        print(f"{r.name.normalized:28s} {str(r.version):12s} {(r.size or 0)/1e6:7.1f} MB")
    print("total %.1f MB"%(tot/1e6))
    if len(sys.argv)>2:
        await rattler.install(recs, target_prefix=sys.argv[2], platform=rattler.Platform("emscripten-wasm32"), show_progress=False)
        print("installed to", sys.argv[2])
asyncio.run(main(sys.argv[1].split(',')))
