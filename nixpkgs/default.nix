{}:

let

common-src = builtins.fetchTarball {
    name = "common-2023-10-25";
    url = https://github.com/avanov/nix-common/archive/d01ad7ed6571f119aa22d86bd31b989cb244474a.tar.gz;
    # Hash obtained using `nix-prefetch-url --unpack <url>`
    sha256 = "sha256:1ji0sa4f5qzffpid1ldncw8nkspg8nzvjwkvw4bqhi843h00k983";
};

overlays = import ./overlays.nix {};
pkgs     = (import common-src { projectOverlays = [ overlays.globalPackageOverlay ]; }).pkgs;

in

{
    inherit pkgs;
}
