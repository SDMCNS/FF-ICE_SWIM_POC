import { execSync } from 'child_process';

console.log('===============================================================');
console.log('🚀 RUNNING COMPLETE MASTER FF-ICE TEST SUITE (PHASES 1 - 4)');
console.log('===============================================================\n');

const testScripts = [
  'tests/phase1-data.test.ts',
  'tests/phase2-trajectory.test.ts',
  'tests/phase3-fixm.test.ts',
  'tests/phase4-swim.test.ts'
];

let allPassed = true;

for (const script of testScripts) {
  console.log(`\n>>> Executing ${script}...`);
  try {
    const out = execSync(`npx tsx ${script}`, { stdio: 'inherit' });
    console.log(`✅ ${script} PASSED`);
  } catch (err) {
    console.error(`❌ ${script} FAILED`);
    allPassed = false;
    process.exit(1);
  }
}

console.log('\n===============================================================');
console.log('🎉 ALL FF-ICE MASTER TESTS PASSED WITH 100% SUCCESS!');
console.log('===============================================================\n');

