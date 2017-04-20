/*
* Natural Sort algorithm for Javascript
* Version 0.2
* Author: Jim Palmer (based on chunking idea from Dave Koelle)
* Released under MIT license.
*/
function naturalSort (a, b) {
// setup temp-scope variables for comparison evauluation
var x = a.toString().toLowerCase() || '', y = b.toString().toLowerCase() || '',
nC = String.fromCharCode(0),
xN = x.replace(/([-]{0,1}[0-9.]{1,})/g, nC + '$1' + nC).split(nC),
yN = y.replace(/([-]{0,1}[0-9.]{1,})/g, nC + '$1' + nC).split(nC),
xD = (new Date(x)).getTime(), yD = (new Date(y)).getTime();
// natural sorting of dates
if ( xD && yD && xD < yD )
return -1;
else if ( xD && yD && xD > yD )
return 1;
// natural sorting through split numeric strings and default strings
for ( var cLoc=0, numS = Math.max( xN.length, yN.length ); cLoc < numS; cLoc++ )
if ( ( parseFloat( xN[cLoc] ) || xN[cLoc] ) < ( parseFloat( yN[cLoc] ) || yN[cLoc] ) )
return -1;
else if ( ( parseFloat( xN[cLoc] ) || xN[cLoc] ) > ( parseFloat( yN[cLoc] ) || yN[cLoc] ) )
return 1;
return 0;
}

jQuery.fn.dataTableExt.oSort['natural-asc'] = function(a,b) {
return naturalSort(a,b);
};

jQuery.fn.dataTableExt.oSort['natural-desc'] = function(a,b) {
return naturalSort(a,b) * -1;
};
