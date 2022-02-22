#!/usr/bin/bash

osc info 2>/dev/null | grep -q obs-to-maven
if test $? -ne 0; then
    echo "Run from a working copy of an obs-to-maven package branch"
    exit 1
fi

RELEASE=$1

if test "z$RELEASE" = "z"; then
    echo "Provide the release version number as parameter"
    exit 1
fi

# remove the old release tarball
osc rm *.orig.tar.gz

curl -L -o obs-to-maven_$RELEASE.orig.tar.gz https://github.com/uyuni-project/obs-to-maven/archive/refs/tags/v$RELEASE.tar.gz
osc add obs-to-maven_$RELEASE.orig.tar.gz

# Update version in spec and dsc
sed -i "s/^Version: \(.*\)/Version: $RELEASE-1/" obs-to-maven.dsc
sed -i "s/^Version: \(.*\)/Version:\t$RELEASE/" obs-to-maven.spec

# Update the Debtransform-Tar in dsc
sed -i "s/^Debtransform-Tar.*\$/Debtransform-Tar: obs-to-maven_$RELEASE.orig.tar.gz/" obs-to-maven.dsc

# Input changelog
osc vc

# Update debian changelog
tar xf debian.tar.xz
CHANGES=`sed -n '4,/^$/p' obs-to-maven.changes | grep '^ \+\*'`

cat - debian/changelog >debian/changelog.new << EOF
obs-to-maven ($RELEASE-1) unstable; urgency=medium

$CHANGES

 -- `osc whois | sed 's/^[^:]\+: //' | tr -d '"'` `date -R`

EOF
mv debian/changelog.new debian/changelog
tar cJf debian.tar.xz debian
rm -r debian

# Update the checksums in the dsc
sed -i '/^\(Checksums-\|Files:\| [[:xdigit:]]\+ [[:digit:]]\+ [^ ]\+tar.*$\)/d' obs-to-maven.dsc
for sum in "sha1" "sha256" "md5"; do
    if test "$sum" = "md5"; then
        echo "Files:" >>obs-to-maven.dsc
    else
        echo "Checksums-$sum:" >>obs-to-maven.dsc
    fi

    for tar_file in `ls *.tar.*`; do
       echo " $(${sum}sum $tar_file | cut -d ' ' -f1) $(du -b $tar_file | cut -f1) $tar_file" >>obs-to-maven.dsc
    done
done

exit 0
