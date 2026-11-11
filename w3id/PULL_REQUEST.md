# w3id.org registration (draft)

Draft of the pull request to [perma-id/w3id.org](https://github.com/perma-id/w3id.org)
that registers `https://w3id.org/managraph/`. Guide:
<https://github.com/perma-id/w3id.org/blob/master/docs/guides/create-an-id.md>.

`managraph/.htaccess` goes to `ids/managraph/.htaccess` in that repo. Nothing
else is added there: w3id only redirects, it does not host files.

## Before opening it

- [ ] The ManaGraph repo is public.
- [ ] GitHub Pages is live at `https://guyschnidrig.github.io/ManaGraph/`.
- [ ] `https://guyschnidrig.github.io/ManaGraph/ontology/managraph.ttl` exists
      (one merged file of `ontology/*.ttl`) and is served as `text/turtle`:
      `curl -sIL <url> | grep -iE '^(HTTP|content-type)'`
- [ ] `https://guyschnidrig.github.io/ManaGraph/ontology/` has HTML documentation.
- [ ] If the IRI scheme in `src/managraph/iri.py` changed, update the rules here.

## Steps

```sh
# fork perma-id/w3id.org on GitHub, then:
git clone --depth 1 https://github.com/<you>/w3id.org.git
cd w3id.org
git switch -c managraph
mkdir ids/managraph
cp <ManaGraph>/w3id/managraph/.htaccess ids/managraph/

(cd tools/check && npm ci)
node tools/check/bin/w3id-check.js        # must be clean
git diff --stat origin/master              # only ids/managraph/

git add ids/managraph/.htaccess
git commit -m "managraph: add identifier for the ManaGraph knowledge graph"
git push -u origin managraph
```

Open the PR from that branch. One identifier per PR, one squashed commit.

## PR title

managraph: add identifier for the ManaGraph knowledge graph

## PR description

Adds `https://w3id.org/managraph/` for ManaGraph, an open linked data
knowledge graph of Magic: The Gathering cards
(https://github.com/GuySchnidrig/ManaGraph).

- `/managraph/ontology` is the ontology. It returns 303 to Turtle for
  `Accept: text/turtle` and to the HTML documentation otherwise. Terms are hash
  IRIs (`/managraph/ontology#Card`).
- Everything else (`/managraph/card/{id}`, `/managraph/printing/{id}`,
  `/managraph/set/{code}`, ...) returns 302 to the same path on the project's
  GitHub Pages site.

Maintainer: Dr. Guy Schnidrig (@GuySchnidrig, ORCID https://orcid.org/0009-0003-8320-8498)
