#!/bin/bash 

target=`pwd`/target

echo rm -rf $target
rm -rf target
echo mvn assembly:assembly
mvn assembly:assembly
jar=`echo $target/jvmconnector-*-SNAPSHOT-jar-with-dependencies.jar`
jarjar=${jar%.*}-jarjar.jar
echo java -jar ${target}/../release/jarjar-1.0.jar process ${target}/../release/jarjar_rules.txt $jar $jarjar
java -jar ${target}/../release/jarjar-1.0.jar process ${target}/../release/jarjar_rules.txt $jar $jarjar
echo unzip -d $target $jar META-INF/MANIFEST.MF
unzip -d $target $jar META-INF/MANIFEST.MF
echo jar ufm $jarjar $target/META-INF/MANIFEST.MF
jar ufm $jarjar $target/META-INF/MANIFEST.MF
echo mv $jarjar $jar
mv $jarjar $jar