// Deployed to capital-connect-demo-bot and capital-connect-demo-bot-v2 only.
// The legacy capital-connect-dashboard endpoint was left unchanged after review.
Deno.serve(() => new Response(JSON.stringify({error:"Simulation service has been retired.",mode:"RETIRED",orders_enabled:false}),{status:410,headers:{"Content-Type":"application/json","Cache-Control":"no-store","Access-Control-Allow-Origin":"*"}}));
