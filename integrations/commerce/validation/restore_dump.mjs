import {PGlite} from '@electric-sql/pglite';
import {pgcrypto} from '@electric-sql/pglite/contrib/pgcrypto';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {gunzipSync} from 'node:zlib';
import {resolve} from 'node:path';
import {access} from 'node:fs/promises';
import {createHash} from 'node:crypto';
const [dumpArg,dataArg,outputArg,migrationArg]=process.argv.slice(2);
if(!dumpArg||!dataArg||!outputArg||!migrationArg)throw Error('Usage: node restore_dump.mjs dump.sql.gz NEW_DATADIR PRIVATE_OUTPUT_DIR migration051.sql');
const dataDir=resolve(dataArg),output=resolve(outputArg);
let exists=false;try{await access(dataDir);exists=true;}catch{}
if(exists)throw Error('Refusing existing data directory; use a fresh disposable target');
await mkdir(output,{recursive:true,mode:0o700});
const compressed=await readFile(dumpArg);
const sql=gunzipSync(compressed).toString('utf8');
const clean=sql.replace(/^\\(?:un)?restrict[^\n]*\n/gm,'');
const db=await PGlite.create(dataDir,{extensions:{pgcrypto}});
const expected=[];let at=0, tables=0;
const regex=/^COPY (public\.[^\n]+?) FROM stdin;\n/gm;
let match;
try {
 while((match=regex.exec(clean))!==null){
  const endRegex=/^\\\.\n/gm;endRegex.lastIndex=regex.lastIndex;const endMatch=endRegex.exec(clean);
  if(!endMatch)throw Error('Missing COPY end marker');
  const end=endMatch.index;
  const prefix=clean.slice(at,match.index);
  if(prefix.trim())await db.exec(prefix);
  const data=clean.slice(regex.lastIndex,end);
  const copy=match[0].replace('FROM stdin;',"FROM '/dev/blob';");
  await db.query(copy,[],{blob:new Blob([data])});
  const table=match[1].slice(0,match[1].indexOf(' ('));
  const expectedRows=data.length?data.split('\n').length-1:0;
  const actual=(await db.query(`SELECT count(*)::int AS n FROM ${table}`)).rows[0].n;
  if(actual!==expectedRows)throw Error('COPY row mismatch for '+table+' expected '+expectedRows+' actual '+actual);
  expected.push({table,rows:actual});tables++;
  at=end+3;regex.lastIndex=at;
 }
 if(clean.slice(at).trim())await db.exec(clean.slice(at));
 console.log('SUPPLEMENTAL_RESTORED_COPY_TABLES',tables);
 const version=(await db.query('SELECT version() AS version')).rows[0].version;
 const counts=(await db.query(`SELECT 'items' AS entity,count(*)::int AS n FROM public.items UNION ALL SELECT 'lots',count(*)::int FROM public.lots UNION ALL SELECT 'products',count(*)::int FROM public.products UNION ALL SELECT 'ecommerce',count(*)::int FROM public.ecommerce UNION ALL SELECT 'orders',count(*)::int FROM public.ecommerce_orders`)).rows;
 await db.exec(await readFile(migrationArg,'utf8'));
 const inventory=(await db.query('SELECT * FROM public.mp_ecommerce_catalog_inventory()')).rows;
 await writeFile(output+'/inventory.json',JSON.stringify(inventory,null,2),{mode:0o600});
 await writeFile(output+'/restore-report.json',JSON.stringify({source_gzip_sha256:createHash('sha256').update(compressed).digest('hex'),runtime:'PGlite supplemental restore; native PostgreSQL16 restore still required',version,table_counts:expected,counts,inventory_rows:inventory.length},null,2),{mode:0o600});
 console.log(JSON.stringify({version,counts,inventory_rows:inventory.length}));
} catch(error) {console.error('RESTORE_FAILED',error.message);process.exitCode=1;} finally {await db.close();}
