package com.arbitrage.engine.architecture;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

/**
 * Lightweight ArchUnit contracts for the dry-run execution sidecar.
 */
@AnalyzeClasses(
        packages = "com.arbitrage.engine",
        importOptions = ImportOption.DoNotIncludeTests.class
)
public class ArchitectureTest {

    @ArchTest
    static final ArchRule liveBrokerMustNotBeUsedOutsideRouter =
            noClasses()
                    .that().resideOutsideOfPackages("com.arbitrage.engine.broker")
                    .should().dependOnClassesThat().haveSimpleName("LiveBroker")
                    .because("LiveBroker is intentionally disabled; routing stays in broker package");

    @ArchTest
    static final ArchRule persistenceShouldNotDependOnGrpcStubs =
            noClasses()
                    .that().resideInAPackage("..persistence..")
                    .should().dependOnClassesThat().resideInAPackage("io.grpc..")
                    .because("persistence layer stays free of gRPC transport types");
}
